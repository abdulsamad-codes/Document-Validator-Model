"""Tests for the automatic post-OCR pipeline chain.

Before this, OCR completing never led anywhere: analysis, confidence,
normalization and rule validation each required their own direct API call,
and nothing in this codebase made those calls. These tests prove the queue
worker now runs that chain automatically once every document job for an
application is terminal, using the same claim/retry/heartbeat machinery
already proven for document processing (see ``app.bulk_queue.workers`` and
``app.bulk_queue.pipeline_runner``).
"""

from __future__ import annotations

from sqlalchemy import select

from app.bulk_queue.pipeline_runner import PipelineRunnerService
from app.bulk_queue.services import BulkQueueService
from app.bulk_queue.workers import ACTION_PIPELINE_BLOCKED, BulkQueueWorker, drain_queue
from app.database.connection import SessionLocal
from app.database.models.audit_log import AuditLog
from app.database.models.enums import ApplicationStatus, JobStatus, JobType
from app.database.models.queue_job import QueueJob
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.extracted_field_repository import ExtractedFieldRepository
from app.database.repositories.queue_job_repository import QueueJobRepository
from app.database.repositories.validation_repository import ValidationRepository
from tests.test_bulk_queue import (
    FailingProcessor,
    SuccessfulProcessor,
    create_application_with_documents,
    enqueue,
)
from tests.test_bulk_upload_api import make_bulk_pdf, upload_bulk
from tests.test_document_analysis_api import BANK_STATEMENT_TEXT
from tests.test_technical_validation_api import create_application
from tests.test_upload_api import upload as upload_single_document

API = "/api/v1"


def pipeline_job_for(application_id: int) -> QueueJob | None:
    """Return the application's pipeline job row, or None."""
    db = SessionLocal()
    try:
        return db.scalars(
            select(QueueJob).where(
                QueueJob.application_id == application_id,
                QueueJob.job_type == JobType.APPLICATION_PIPELINE,
            )
        ).one_or_none()
    finally:
        db.close()


def audit_actions_for(application_id: int) -> list[str]:
    """Return every audit action recorded for an application."""
    db = SessionLocal()
    try:
        return list(
            db.scalars(
                select(AuditLog.action).where(AuditLog.application_id == application_id)
            ).all()
        )
    finally:
        db.close()


def application_status_for(application_id: int) -> str | None:
    """Return the current status of an application."""
    db = SessionLocal()
    try:
        application = ApplicationRepository(db).get_by_id(application_id)
        return application.status.value if application is not None else None
    finally:
        db.close()


def mark_processing(application_id: int) -> None:
    """Set an application's status to PROCESSING directly.

    Mirrors the real precondition every production enqueue call site now
    establishes (see the guarded writes in ``upload/services.py`` and
    ``bulk_queue/services.py``) without going through the full HTTP upload
    flow, matching this module's existing pattern of building queue state
    directly for worker-level tests.
    """
    db = SessionLocal()
    try:
        applications = ApplicationRepository(db)
        application = applications.get_by_id(application_id)
        applications.update(application, status=ApplicationStatus.PROCESSING)
    finally:
        db.close()


def drain_until_empty(*, max_passes: int = 5) -> None:
    """Drain the real queue repeatedly.

    One pass is not always enough: a bulk-split job enqueues new per-document
    jobs mid-drain, and the pipeline job is itself only enqueued after those
    finish, so it needs a later pass to be claimed and run.
    """
    for _ in range(max_passes):
        summary = drain_queue()
        if summary.processed == 0:
            return


# --- Success: 10 real bulk uploads, chained end to end -----------------------


def test_ten_bulk_uploads_each_produce_a_working_report(authenticated_client):
    application_ids = []
    for _ in range(10):
        application_id = create_application(authenticated_client)
        response = upload_bulk(
            authenticated_client,
            application_id,
            make_bulk_pdf([BANK_STATEMENT_TEXT]),
        )
        assert response.status_code == 201, response.text
        start = authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
        assert start.status_code == 200, start.text
        application_ids.append(application_id)

    drain_until_empty()

    for application_id in application_ids:
        job = pipeline_job_for(application_id)
        assert job is not None, f"application {application_id} never got a pipeline job"
        assert job.status is JobStatus.COMPLETED, (
            f"application {application_id} pipeline job ended {job.status}: {job.last_error}"
        )
        response = authenticated_client.get(f"{API}/applications/{application_id}/validation-report")
        assert response.status_code == 200, response.text
        assert application_status_for(application_id) == "PENDING_REVIEW"


def test_bulk_upload_marks_application_processing_immediately(authenticated_client):
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf([BANK_STATEMENT_TEXT]),
    )
    assert response.status_code == 201, response.text

    # No draining yet -- the enqueue itself, not the worker, sets PROCESSING.
    assert application_status_for(application_id) == "PROCESSING"


def test_start_processing_marks_single_upload_application_processing(
    authenticated_client, monkeypatch
):
    """Checks the synchronous portion of /processing/start in isolation.

    Starlette's TestClient runs FastAPI BackgroundTasks synchronously before
    the response is returned, so with background draining enabled the queue
    always fully resolves (to FAILED or PENDING_REVIEW) inside this same
    call, and "PROCESSING" is never observable here regardless of document
    content. Production only gets the true non-blocking behaviour this test
    means to check by running dedicated worker processes with
    ``bulk_queue_background_drain=false`` (see _schedule_drain's docstring)
    -- so disable inline draining here too, the same way production does,
    to isolate start_processing()'s own enqueue-and-mark-PROCESSING step
    from worker execution.

    (Previously this test used the bare conftest PDF_BYTES, which has no
    content stream and always fails technical validation; it happened to
    still observe "PROCESSING" because the bulk queue's old SKIPPED-retry
    timing left a failing job in RETRY_WAITING for one drain pass instead of
    resolving it immediately. That was incidental masking, not the real
    guarantee this test is meant to verify.)
    """
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "bulk_queue_background_drain", False)
    application_id = create_application(authenticated_client)
    upload_response = upload_single_document(authenticated_client, application_id)
    assert upload_response.status_code == 201, upload_response.text
    assert application_status_for(application_id) == "SUBMITTED"

    start = authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
    assert start.status_code == 200, start.text

    assert application_status_for(application_id) == "PROCESSING"


def test_enqueue_does_not_regress_a_decided_application_status():
    """Adding a document after a decision must not resurrect PROCESSING.

    A document can be uploaded to an application after it has already been
    approved/rejected/corrected (upload has no status check). Re-enqueueing
    must not silently move the status backward from a terminal decision.
    """
    application_id, _ = create_application_with_documents(1)
    db = SessionLocal()
    try:
        applications = ApplicationRepository(db)
        application = applications.get_by_id(application_id)
        applications.update(application, status=ApplicationStatus.APPROVED)

        BulkQueueService(db).enqueue_application(application_id=application_id)

        db.refresh(application)
        assert application.status is ApplicationStatus.APPROVED
    finally:
        db.close()


def test_rerunning_the_pipeline_does_not_duplicate_stored_rows(authenticated_client):
    application_id = create_application(authenticated_client)
    upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf([BANK_STATEMENT_TEXT]),
    )
    authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
    drain_until_empty()

    db = SessionLocal()
    try:
        fields_before = len(list(ExtractedFieldRepository(db).get_by_application(application_id)))
        rows_before = len(
            list(ValidationRepository(db).get_by_application(application_id, limit=1000))
        )

        PipelineRunnerService(db).run(application_id=application_id)

        fields_after = len(list(ExtractedFieldRepository(db).get_by_application(application_id)))
        rows_after = len(
            list(ValidationRepository(db).get_by_application(application_id, limit=1000))
        )
    finally:
        db.close()

    assert fields_after == fields_before
    assert rows_after == rows_before


# --- All documents fail: pipeline must not run --------------------------------


def test_pipeline_never_starts_when_zero_documents_processed(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 1)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 0)
    application_id, _ = create_application_with_documents(2)
    enqueue(application_id)
    mark_processing(application_id)

    BulkQueueWorker(settings=settings, processor_factory=FailingProcessor).run_until_empty()

    job = pipeline_job_for(application_id)
    assert job is None, "pipeline job must not be enqueued when nothing succeeded"
    assert ACTION_PIPELINE_BLOCKED in audit_actions_for(application_id)
    assert application_status_for(application_id) == "PROCESSING_FAILED", (
        "an application where every document fails must end up visibly "
        "distinguishable, not silently stuck at PROCESSING"
    )


# --- Partial failure: pipeline must still run on what succeeded --------------


def test_pipeline_starts_once_on_partial_success(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 1)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 0)
    application_id, document_ids = create_application_with_documents(3)
    enqueue(application_id)
    failing_ids = set(document_ids[:1])

    class HalfFailProcessor:
        def __init__(self, db):
            self._db = db
            self._inner_success = SuccessfulProcessor(db)

        def process_one(self, *, application_id: int, document_id: int):
            if document_id in failing_ids:
                raise RuntimeError("simulated permanent failure")
            return self._inner_success.process_one(
                application_id=application_id, document_id=document_id
            )

    BulkQueueWorker(settings=settings, processor_factory=HalfFailProcessor).run_until_empty()

    job = pipeline_job_for(application_id)
    assert job is not None, "pipeline job should start once at least one document succeeded"


# --- Race safety: concurrent-enqueue guard ------------------------------------


def test_pipeline_job_enqueued_at_most_once_under_a_race():
    application_id, _ = create_application_with_documents(1)
    db = SessionLocal()
    try:
        jobs = QueueJobRepository(db)
        first = jobs.try_enqueue_pipeline_job(application_id=application_id, max_attempts=3)
        second = jobs.try_enqueue_pipeline_job(application_id=application_id, max_attempts=3)
        assert first is not None
        assert second is None

        rows = db.scalars(
            select(QueueJob).where(
                QueueJob.application_id == application_id,
                QueueJob.job_type == JobType.APPLICATION_PIPELINE,
            )
        ).all()
        assert len(rows) == 1
    finally:
        db.close()
