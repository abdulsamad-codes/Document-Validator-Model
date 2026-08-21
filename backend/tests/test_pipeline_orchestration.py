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

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.bulk_queue.pipeline_runner import PipelineRunnerService
from app.bulk_queue.services import BulkQueueService
from app.bulk_queue.workers import ACTION_PIPELINE_BLOCKED, ACTION_PIPELINE_FAILED, BulkQueueWorker, drain_queue
from app.core.config import get_settings
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


# --- Pipeline failure handling: application must not stay stuck at PROCESSING -


def test_pipeline_job_failure_marks_application_processing_failed(monkeypatch):
    """When the APPLICATION_PIPELINE job permanently fails the application
    must not stay silently stuck at PROCESSING. It must move to
    PROCESSING_FAILED with an audit trail so operators can investigate."""
    from app.core.config import get_settings
    from unittest.mock import MagicMock

    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 1)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 0)

    application_id, _ = create_application_with_documents(1)
    enqueue(application_id)
    mark_processing(application_id)

    # Enqueue a pipeline job directly (simulating what _maybe_start_pipeline does)
    db = SessionLocal()
    try:
        pipeline_job = QueueJobRepository(db).try_enqueue_pipeline_job(
            application_id=application_id, max_attempts=1,
        )
        assert pipeline_job is not None
    finally:
        db.close()

    class FailingPipelineRunner:
        def __init__(self, db):
            self._db = db

        def run(self, *, application_id: int):
            raise RuntimeError("simulated pipeline stage failure")

    # First claim the document OCR job to completion, then the pipeline job
    BulkQueueWorker(settings=settings, processor_factory=SuccessfulProcessor).run_until_empty()

    # Now run with a failing pipeline runner
    BulkQueueWorker(
        settings=settings,
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=FailingPipelineRunner,
    ).run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None
    assert pipeline.status is JobStatus.FAILED, (
        f"pipeline job should be FAILED, got {pipeline.status}: {pipeline.last_error}"
    )
    assert application_status_for(application_id) == "PROCESSING_FAILED", (
        "application must not stay stuck at PROCESSING when the pipeline "
        "permanently fails"
    )
    assert ACTION_PIPELINE_FAILED in audit_actions_for(application_id), (
        "a pipeline failure must be recorded in the audit log"
    )


def test_pipeline_retry_then_success_leaves_application_pending_review(monkeypatch):
    """A pipeline job that fails once then succeeds on retry must leave
    the application at PENDING_REVIEW, not PROCESSING or PROCESSING_FAILED."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 2)
    # Use a non-zero backoff so the RETRY_WAITING job is not immediately claimable.
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 60)

    application_id, _ = create_application_with_documents(1)
    enqueue(application_id)
    mark_processing(application_id)

    call_count = 0

    class RetryThenSucceedPipeline:
        def __init__(self, db):
            self._db = db

        def run(self, *, application_id: int):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient pipeline failure")
            # Second call: just mark pending review (real pipeline does analysis etc.)
            from app.bulk_queue.pipeline_runner import PipelineRunnerService
            PipelineRunnerService(self._db)._mark_pending_review(application_id)

    # First pass: document OCR succeeds, pipeline is enqueued by _maybe_start_pipeline,
    # then the pipeline job runs and fails (call_count=1).
    worker = BulkQueueWorker(
        settings=settings,
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=RetryThenSucceedPipeline,
    )
    worker.run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None, "pipeline job must exist after first pass"
    # Pipeline failed on first attempt, should be RETRY_WAITING (backoff prevents re-claim)
    assert pipeline.status is JobStatus.RETRY_WAITING, (
        f"pipeline should be RETRY_WAITING, got {pipeline.status}"
    )

    # Simulate time passing so the retry backoff expires.
    db = SessionLocal()
    try:
        pj = db.scalars(
            select(QueueJob).where(
                QueueJob.application_id == application_id,
                QueueJob.job_type == JobType.APPLICATION_PIPELINE,
            )
        ).one()
        pj.retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()

    # Second pass: pipeline retries and succeeds (call_count=2)
    worker2 = BulkQueueWorker(
        settings=settings,
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=RetryThenSucceedPipeline,
    )
    worker2.run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None
    assert pipeline.status is JobStatus.COMPLETED
    assert application_status_for(application_id) == "PENDING_REVIEW"


def test_pipeline_failure_does_not_overwrite_human_decision(monkeypatch):
    """If a human has already decided on an application (APPROVED/REJECTED),
    a pipeline failure must not revert the status to PROCESSING_FAILED."""
    from app.core.config import get_settings
    from app.bulk_queue.workers import BulkQueueWorker

    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 1)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 0)

    application_id, _ = create_application_with_documents(1)
    enqueue(application_id)

    # Set up: documents succeed, pipeline job is enqueued, then human decides
    db = SessionLocal()
    try:
        # Mark all document jobs completed
        jobs_repo = QueueJobRepository(db)
        for job in jobs_repo.list_by_application(application_id):
            if job.job_type is JobType.DOCUMENT_OCR:
                jobs_repo.mark_completed(job)

        # Enqueue pipeline job
        pipeline_job = jobs_repo.try_enqueue_pipeline_job(
            application_id=application_id, max_attempts=1,
        )
        assert pipeline_job is not None

        # Simulate human decision AFTER pipeline was enqueued
        applications = ApplicationRepository(db)
        application = applications.get_by_id(application_id)
        applications.update(application, status=ApplicationStatus.APPROVED)
        db.commit()
    finally:
        db.close()

    # Now simulate the pipeline job failing permanently
    class FailingPipelineRunner:
        def __init__(self, db):
            self._db = db

        def run(self, *, application_id: int):
            raise RuntimeError("simulated pipeline stage failure")

    BulkQueueWorker(
        settings=settings,
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=FailingPipelineRunner,
    ).run_until_empty()

    # The human decision must be preserved -- _handle_pipeline_failure checks
    # that status is PROCESSING before overwriting
    assert application_status_for(application_id) == "APPROVED", (
        "a pipeline failure must not overwrite a human decision"
    )


def test_validation_report_exists_after_rule_failure(authenticated_client):
    """A business validation failure (e.g. IBAN mismatch) must still produce
    a Validation Report. The report is a read-only aggregation of stored data,
    not a pass/fail gate."""
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf([BANK_STATEMENT_TEXT]),
    )
    assert response.status_code == 201, response.text
    authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
    drain_until_empty()

    # The pipeline should have completed with PENDING_REVIEW
    assert application_status_for(application_id) == "PENDING_REVIEW"

    # The validation report must exist regardless of individual rule outcomes
    report_response = authenticated_client.get(
        f"{API}/applications/{application_id}/validation-report"
    )
    assert report_response.status_code == 200, (
        f"validation report must be generable even with rule failures: {report_response.text}"
    )
    report_data = report_response.json()
    assert "overall_status" in report_data
    assert "rule_summary" in report_data
    assert report_data["rule_summary"]["total"] > 0, "rules must have been executed"


def test_full_end_to_end_upload_through_validation_report(authenticated_client):
    """End-to-end integration: upload → queue → OCR → analysis → confidence →
    normalization → rule engine → validation report exists → application at
    PENDING_REVIEW."""
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf([BANK_STATEMENT_TEXT]),
    )
    assert response.status_code == 201, response.text
    authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
    drain_until_empty()

    # Pipeline completed
    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None, "pipeline job must exist"
    assert pipeline.status is JobStatus.COMPLETED, (
        f"pipeline must complete, got {pipeline.status}: {pipeline.last_error}"
    )

    # Application moved to PENDING_REVIEW
    assert application_status_for(application_id) == "PENDING_REVIEW"

    # Validation report is generable
    report_response = authenticated_client.get(
        f"{API}/applications/{application_id}/validation-report"
    )
    assert report_response.status_code == 200, report_response.text

    # Extracted fields exist
    db = SessionLocal()
    try:
        fields = list(ExtractedFieldRepository(db).get_by_application(application_id))
        assert len(fields) > 0, "extracted fields must exist after pipeline"
    finally:
        db.close()

    # Validation results exist
    db = SessionLocal()
    try:
        validation_rows = list(
            ValidationRepository(db).get_by_application(application_id, limit=1000)
        )
        assert len(validation_rows) > 0, "validation results must exist after pipeline"
    finally:
        db.close()


# --- State-transition matrix: terminal states for every pipeline outcome -------
#
# This matrix protects against future queue/pipeline changes by explicitly
# asserting the application status, pipeline job status and audit trail for
# every terminal condition.  Each row is an independent test that creates
# its own application, drives the worker through a specific scenario, and
# asserts the expected terminal state.
#
# | Situation                            | Expected                              |
# |--------------------------------------|---------------------------------------|
# | Pipeline succeeds                    | PENDING_REVIEW                        |
# | Pipeline permanently fails           | PROCESSING_FAILED                     |
# | OCR permanently fails                | PROCESSING_FAILED                     |
# | Reviewer already decided             | Decision remains unchanged           |
# | Pipeline retries then succeeds       | PENDING_REVIEW                        |
# | Pipeline retries then permanently fails | PROCESSING_FAILED                  |
# | Pipeline failure                     | APPLICATION_PIPELINE_FAILED audit     |
# | Successful pipeline                  | No false failure audit                |


def _setup_application_with_documents(
    monkeypatch,
    *,
    num_docs: int = 1,
    max_attempts: int = 1,
    retry_backoff: int = 0,
) -> tuple[int, list[int]]:
    """Create an application, enqueue its documents, mark it PROCESSING.

    Returns the application id and document ids."""
    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", max_attempts)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", retry_backoff)

    application_id, document_ids = create_application_with_documents(num_docs)
    enqueue(application_id)
    mark_processing(application_id)
    return application_id, document_ids


def _enqueue_pipeline_job(
    application_id: int,
    *,
    max_attempts: int = 1,
) -> QueueJob:
    """Enqueue an APPLICATION_PIPELINE job for the given application."""
    db = SessionLocal()
    try:
        job = QueueJobRepository(db).try_enqueue_pipeline_job(
            application_id=application_id,
            max_attempts=max_attempts,
        )
        assert job is not None, "pipeline job enqueue must succeed"
        return job
    finally:
        db.close()


def _complete_document_jobs(application_id: int) -> None:
    """Mark every DOCUMENT_OCR job for the application as COMPLETED."""
    db = SessionLocal()
    try:
        jobs_repo = QueueJobRepository(db)
        for job in jobs_repo.list_by_application(application_id):
            if job.job_type is JobType.DOCUMENT_OCR:
                jobs_repo.mark_completed(job)
    finally:
        db.close()


def _expire_retry_backoff(application_id: int) -> None:
    """Set the pipeline job's retry_at to the past so it becomes claimable."""
    db = SessionLocal()
    try:
        pj = db.scalars(
            select(QueueJob).where(
                QueueJob.application_id == application_id,
                QueueJob.job_type == JobType.APPLICATION_PIPELINE,
            )
        ).one()
        pj.retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()


# -- Row 1: Pipeline succeeds → PENDING_REVIEW ---------------------------------

def test_state_matrix_pipeline_succeeds(monkeypatch):
    """Situation: pipeline succeeds on first attempt.
    Expected:  application status = PENDING_REVIEW,
               pipeline job = COMPLETED,
               no failure audit."""
    application_id, _ = _setup_application_with_documents(
        monkeypatch, num_docs=1, max_attempts=1,
    )
    _enqueue_pipeline_job(application_id)
    _complete_document_jobs(application_id)

    class SucceedPipeline:
        def __init__(self, db):
            self._db = db
        def run(self, *, application_id: int):
            PipelineRunnerService(self._db)._mark_pending_review(application_id)

    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=SucceedPipeline,
    ).run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None
    assert pipeline.status is JobStatus.COMPLETED
    assert application_status_for(application_id) == "PENDING_REVIEW"
    assert ACTION_PIPELINE_FAILED not in audit_actions_for(application_id)


# -- Row 2: Pipeline permanently fails → PROCESSING_FAILED ---------------------

def test_state_matrix_pipeline_permanent_failure(monkeypatch):
    """Situation: pipeline permanently fails (max_attempts=1, first try).
    Expected:  application status = PROCESSING_FAILED,
               pipeline job = FAILED,
               APPLICATION_PIPELINE_FAILED audit exists."""
    application_id, _ = _setup_application_with_documents(
        monkeypatch, num_docs=1, max_attempts=1,
    )
    _enqueue_pipeline_job(application_id)
    _complete_document_jobs(application_id)

    class FailingPipeline:
        def __init__(self, db):
            self._db = db
        def run(self, *, application_id: int):
            raise RuntimeError("permanent pipeline failure")

    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=FailingPipeline,
    ).run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None
    assert pipeline.status is JobStatus.FAILED
    assert application_status_for(application_id) == "PROCESSING_FAILED"
    assert ACTION_PIPELINE_FAILED in audit_actions_for(application_id)


# -- Row 3: OCR permanently fails → PROCESSING_FAILED --------------------------

def test_state_matrix_ocr_permanent_failure(monkeypatch):
    """Situation: every document OCR job fails permanently.
    Expected:  application status = PROCESSING_FAILED,
               no pipeline job enqueued,
               PIPELINE_BLOCKED audit exists."""
    application_id, _ = _setup_application_with_documents(
        monkeypatch, num_docs=2, max_attempts=1,
    )

    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=FailingProcessor,
    ).run_until_empty()

    assert pipeline_job_for(application_id) is None
    assert application_status_for(application_id) == "PROCESSING_FAILED"
    assert ACTION_PIPELINE_BLOCKED in audit_actions_for(application_id)
    assert ACTION_PIPELINE_FAILED not in audit_actions_for(application_id)


# -- Row 4: Reviewer already decided → decision remains unchanged ---------------

def test_state_matrix_reviewer_decision_preserved(monkeypatch):
    """Situation: human already decided (APPROVED), then pipeline job fails.
    Expected:  application status remains APPROVED."""
    application_id, _ = _setup_application_with_documents(
        monkeypatch, num_docs=1, max_attempts=1,
    )
    _enqueue_pipeline_job(application_id)
    _complete_document_jobs(application_id)

    # Human decides BEFORE pipeline runs
    db = SessionLocal()
    try:
        apps = ApplicationRepository(db)
        app = apps.get_by_id(application_id)
        apps.update(app, status=ApplicationStatus.APPROVED)
        db.commit()
    finally:
        db.close()

    class FailingPipeline:
        def __init__(self, db):
            self._db = db
        def run(self, *, application_id: int):
            raise RuntimeError("too late, human already decided")

    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=FailingPipeline,
    ).run_until_empty()

    assert application_status_for(application_id) == "APPROVED"

    # Also test REJECTED
    application_id2, _ = _setup_application_with_documents(
        monkeypatch, num_docs=1, max_attempts=1,
    )
    _enqueue_pipeline_job(application_id2)
    _complete_document_jobs(application_id2)

    db = SessionLocal()
    try:
        apps = ApplicationRepository(db)
        app = apps.get_by_id(application_id2)
        apps.update(app, status=ApplicationStatus.REJECTED)
        db.commit()
    finally:
        db.close()

    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=FailingPipeline,
    ).run_until_empty()

    assert application_status_for(application_id2) == "REJECTED"


# -- Row 5: Pipeline retries then succeeds → PENDING_REVIEW ---------------------

def test_state_matrix_retry_then_succeed(monkeypatch):
    """Situation: pipeline fails on first try, succeeds on retry.
    Expected:  application status = PENDING_REVIEW,
               pipeline job = COMPLETED."""
    application_id, _ = _setup_application_with_documents(
        monkeypatch, num_docs=1, max_attempts=2, retry_backoff=60,
    )
    _enqueue_pipeline_job(application_id, max_attempts=2)
    _complete_document_jobs(application_id)

    call_count = 0

    class RetrySucceedPipeline:
        def __init__(self, db):
            self._db = db
        def run(self, *, application_id: int):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient failure")
            PipelineRunnerService(self._db)._mark_pending_review(application_id)

    # First pass: pipeline fails, job goes to RETRY_WAITING
    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=RetrySucceedPipeline,
    ).run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None
    assert pipeline.status is JobStatus.RETRY_WAITING
    assert application_status_for(application_id) == "PROCESSING"

    # Expire the backoff
    _expire_retry_backoff(application_id)

    # Second pass: pipeline succeeds
    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=RetrySucceedPipeline,
    ).run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline.status is JobStatus.COMPLETED
    assert application_status_for(application_id) == "PENDING_REVIEW"


# -- Row 6: Pipeline retries then permanently fails → PROCESSING_FAILED ---------

def test_state_matrix_retry_then_permanent_failure(monkeypatch):
    """Situation: pipeline fails twice (max_attempts=2), exhausts budget.
    Expected:  application status = PROCESSING_FAILED,
               pipeline job = FAILED."""
    application_id, _ = _setup_application_with_documents(
        monkeypatch, num_docs=1, max_attempts=2, retry_backoff=60,
    )
    _enqueue_pipeline_job(application_id, max_attempts=2)
    _complete_document_jobs(application_id)

    class AlwaysFailPipeline:
        def __init__(self, db):
            self._db = db
        def run(self, *, application_id: int):
            raise RuntimeError("persistent pipeline failure")

    # First pass: fails, RETRY_WAITING
    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=AlwaysFailPipeline,
    ).run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline.status is JobStatus.RETRY_WAITING

    # Expire backoff and run second attempt
    _expire_retry_backoff(application_id)
    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=AlwaysFailPipeline,
    ).run_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline.status is JobStatus.FAILED
    assert application_status_for(application_id) == "PROCESSING_FAILED"
    assert ACTION_PIPELINE_FAILED in audit_actions_for(application_id)


# -- Row 7: Pipeline failure → APPLICATION_PIPELINE_FAILED audit ----------------

def test_state_matrix_pipeline_failure_audit_recorded(monkeypatch):
    """Situation: pipeline job permanently fails.
    Expected:  APPLICATION_PIPELINE_FAILED audit entry exists with error detail."""
    application_id, _ = _setup_application_with_documents(
        monkeypatch, num_docs=1, max_attempts=1,
    )
    _enqueue_pipeline_job(application_id)
    _complete_document_jobs(application_id)

    class FailingPipeline:
        def __init__(self, db):
            self._db = db
        def run(self, *, application_id: int):
            raise RuntimeError("stage X crashed")

    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=FailingPipeline,
    ).run_until_empty()

    actions = audit_actions_for(application_id)
    assert ACTION_PIPELINE_FAILED in actions

    # Verify audit entry contains error detail
    db = SessionLocal()
    try:
        entry = db.scalars(
            select(AuditLog).where(
                AuditLog.application_id == application_id,
                AuditLog.action == ACTION_PIPELINE_FAILED,
            )
        ).one()
        assert entry.details is not None
        assert "last_error" in entry.details
        assert "stage X crashed" in entry.details["last_error"]
    finally:
        db.close()


# -- Row 8: Successful pipeline → no false failure audit -----------------------

def test_state_matrix_success_no_false_failure_audit(monkeypatch):
    """Situation: pipeline succeeds on first attempt.
    Expected:  no APPLICATION_PIPELINE_FAILED or PIPELINE_BLOCKED audit."""
    application_id, _ = _setup_application_with_documents(
        monkeypatch, num_docs=1, max_attempts=1,
    )
    _enqueue_pipeline_job(application_id)
    _complete_document_jobs(application_id)

    class SucceedPipeline:
        def __init__(self, db):
            self._db = db
        def run(self, *, application_id: int):
            PipelineRunnerService(self._db)._mark_pending_review(application_id)

    BulkQueueWorker(
        settings=get_settings(),
        processor_factory=SuccessfulProcessor,
        pipeline_runner_factory=SucceedPipeline,
    ).run_until_empty()

    actions = audit_actions_for(application_id)
    assert ACTION_PIPELINE_FAILED not in actions, (
        f"successful pipeline must not record {ACTION_PIPELINE_FAILED}, "
        f"got: {actions}"
    )
    assert ACTION_PIPELINE_BLOCKED not in actions, (
        f"successful pipeline must not record {ACTION_PIPELINE_BLOCKED}, "
        f"got: {actions}"
    )


# -- Bulk-upload variant: pipeline succeeds end-to-end --------------------------

def test_state_matrix_bulk_upload_pipeline_succeeds(authenticated_client):
    """Full real-data path through the bulk upload + worker pipeline.
    Expected:  PENDING_REVIEW, validation report generable."""
    application_id = create_application(authenticated_client)
    response = upload_bulk(
        authenticated_client,
        application_id,
        make_bulk_pdf([BANK_STATEMENT_TEXT]),
    )
    assert response.status_code == 201, response.text
    authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
    drain_until_empty()

    pipeline = pipeline_job_for(application_id)
    assert pipeline is not None
    assert pipeline.status is JobStatus.COMPLETED
    assert application_status_for(application_id) == "PENDING_REVIEW"

    report = authenticated_client.get(
        f"{API}/applications/{application_id}/validation-report"
    )
    assert report.status_code == 200

    actions = audit_actions_for(application_id)
    assert ACTION_PIPELINE_FAILED not in actions
