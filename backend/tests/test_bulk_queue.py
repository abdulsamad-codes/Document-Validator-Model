"""Tests for the persistent bulk processing queue."""

from __future__ import annotations

import multiprocessing
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

import pymupdf
import pytest

from app.bulk_queue.workers import BulkQueueWorker, drain_queue
from app.core.security import hash_password
from app.core.config import get_settings
from app.database.connection import SessionLocal
from app.database.models.document import Document
from app.database.models.enums import DocumentProcessingStatus, DocumentType, JobStatus
from app.database.models.queue_job import QueueJob
from app.database.models.user import User
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.queue_job_repository import QueueJobRepository
from app.document_processing.schemas import DocumentProcessingResult, ProcessingOutcome
from app.document_processing.services import DocumentProcessingService
from tests.test_bulk_upload_api import make_bulk_pdf, upload_bulk
from tests.test_document_processing_api import FakeOCREngine
from tests.test_technical_validation_api import create_application

API = "/api/v1"


class SuccessfulProcessor:
    """Fake processor that avoids OCR/AI work."""

    def __init__(self, db):
        self._db = db

    def process_one(self, *, application_id: int, document_id: int):
        document = self._db.get(Document, document_id)
        document.processing_status = DocumentProcessingStatus.COMPLETED
        self._db.add(document)
        self._db.commit()
        return DocumentProcessingResult(
            document_id=document_id,
            file_name=document.original_filename,
            outcome=ProcessingOutcome.PROCESSED,
        )


class FailingProcessor:
    """Fake processor that raises a recoverable processing error."""

    def __init__(self, db):
        self._db = db

    def process_one(self, *, application_id: int, document_id: int):
        raise RuntimeError("transient failure")


class SleepingProcessor:
    """Fake processor used by the concurrency benchmark."""

    active = 0
    max_active = 0
    lock = Lock()

    def __init__(self, db):
        self._db = db

    def process_one(self, *, application_id: int, document_id: int):
        with self.lock:
            type(self).active += 1
            type(self).max_active = max(type(self).max_active, type(self).active)
        time.sleep(0.03)
        document = self._db.get(Document, document_id)
        document.processing_status = DocumentProcessingStatus.COMPLETED
        self._db.add(document)
        self._db.commit()
        with self.lock:
            type(self).active -= 1
        return DocumentProcessingResult(
            document_id=document_id,
            file_name=document.original_filename,
            outcome=ProcessingOutcome.PROCESSED,
        )


#: Claim log directory used by the multi-process duplicate-claim test. Each
#: worker process gets its own file (named after its pid) rather than
#: appending to one shared file: concurrent same-file appends from separate
#: OS processes are atomic in practice on POSIX but not reliably so on
#: Windows, and a failed write here would fail the fake processor and push
#: the job onto a 30s+ retry backoff, not just lose a line. One file per
#: writer sidesteps the question entirely; the test merges them afterwards.
_record_dir: str | None = None


class RecordProcessor:
    """Fake processor that records every processed document id to its own file."""

    def __init__(self, db):
        self._db = db

    def process_one(self, *, application_id: int, document_id: int):
        document = self._db.get(Document, document_id)
        document.processing_status = DocumentProcessingStatus.COMPLETED
        self._db.add(document)
        self._db.commit()
        record_path = Path(_record_dir) / f"{os.getpid()}.txt"
        with open(record_path, "a", encoding="utf-8") as handle:
            handle.write(f"{document_id}\n")
        return DocumentProcessingResult(
            document_id=document_id,
            file_name=document.original_filename,
            outcome=ProcessingOutcome.PROCESSED,
        )


def _drain_in_child_process(record_dir: str) -> None:
    """Drain the queue from a forked worker process.

    Args:
        record_dir: Directory each worker writes its own claim log into.
    """
    global _record_dir
    _record_dir = record_dir
    from app.database.connection import engine

    # Inherited pooled connections from the parent must never be reused.
    engine.dispose()
    worker = BulkQueueWorker(processor_factory=RecordProcessor)
    worker.run_until_empty()


def create_application_with_documents(count: int) -> tuple[int, list[int]]:
    """Create an application and uploaded documents directly in the database."""
    db = SessionLocal()
    try:
        application = ApplicationRepository(db).create(created_by="queue-test")
        docs = []
        for index in range(count):
            docs.append(
                Document(
                    application_id=application.id,
                    document_type=DocumentType.OTHER_SUPPORTING_DOCUMENT,
                    copy_number=index + 1,
                    original_filename=f"doc-{index + 1}.pdf",
                    stored_file_path=f"applications/test/doc-{index + 1}.pdf",
                    file_type="application/pdf",
                    processing_status=DocumentProcessingStatus.UPLOADED,
                )
            )
        DocumentRepository(db).create_many(documents=docs)
        return application.id, [document.id for document in docs]
    finally:
        db.close()


def enqueue(application_id: int):
    """Enqueue uploaded documents and return jobs."""
    db = SessionLocal()
    try:
        jobs, _, _ = QueueJobRepository(db).enqueue_uploaded_documents(
            application_id=application_id,
            max_attempts=get_settings().bulk_queue_max_attempts,
        )
        return [(job.id, job.document_id) for job in jobs]
    finally:
        db.close()


def queue_counts(application_id: int) -> dict[JobStatus, int]:
    """Return queue counts for one app."""
    db = SessionLocal()
    try:
        return QueueJobRepository(db).progress_for_application(application_id)
    finally:
        db.close()


def authenticate(client):
    """Create and sign in the operator used by protected processing APIs."""
    db = SessionLocal()
    try:
        db.add(
            User(
                employee_id="QUEUE-OP",
                email="queue-op@example.test",
                name="Queue Operator",
                role="Verification Officer",
                password_hash=hash_password("QueuePass@123"),
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()
    response = client.post(
        f"{API}/auth/login",
        json={"identifier": "QUEUE-OP", "password": "QueuePass@123", "remember": False},
    )
    assert response.status_code == 200, response.text


def test_enqueue_uploaded_documents_and_prevent_duplicates(client):
    authenticate(client)
    application_id, document_ids = create_application_with_documents(3)

    first = client.post(f"{API}/applications/{application_id}/queue/enqueue")
    second = client.post(f"{API}/applications/{application_id}/queue/enqueue")

    assert first.status_code == 200, first.text
    assert first.json()["jobs_created"] == 3
    assert second.status_code == 200, second.text
    assert second.json()["jobs_created"] == 0
    assert second.json()["jobs_existing"] == 3
    assert sorted(job["document_id"] for job in second.json()["jobs"]) == sorted(document_ids)


def test_processing_start_requires_authentication(client):
    application_id, _ = create_application_with_documents(1)
    response = client.post(f"{API}/applications/{application_id}/processing/start")
    assert response.status_code == 401


def test_authenticated_processing_start_and_empty_application(client):
    authenticate(client)
    application_id, _ = create_application_with_documents(1)
    response = client.post(f"{API}/applications/{application_id}/processing/start")
    assert response.status_code == 200, response.text
    assert response.json()["documents_queued"] == 1

    empty_db = SessionLocal()
    try:
        empty_application = ApplicationRepository(empty_db).create(created_by="empty")
    finally:
        empty_db.close()
    empty_response = client.post(
        f"{API}/applications/{empty_application.id}/processing/start"
    )
    assert empty_response.status_code == 200
    assert empty_response.json()["documents_queued"] == 0


def test_processing_progress_reports_business_language(client):
    authenticate(client)
    application_id, _ = create_application_with_documents(4)
    enqueue(application_id)
    db = SessionLocal()
    try:
        jobs = list(QueueJobRepository(db).list_by_application(application_id))
        jobs[0].status = JobStatus.COMPLETED
        jobs[1].status = JobStatus.PROCESSING
        jobs[2].status = JobStatus.FAILED
        db.commit()
    finally:
        db.close()
    response = client.get(f"{API}/applications/{application_id}/processing/progress")
    assert response.status_code == 200
    assert response.json() == {
        "application_id": application_id,
        "total_documents": 4,
        "queued": 1,
        "processing": 1,
        "completed": 1,
        "failed": 1,
        "progress_percentage": 25.0,
        "documents_needing_attention": 1,
    }


def test_retry_failed_documents_does_not_touch_completed(client):
    authenticate(client)
    application_id, _ = create_application_with_documents(2)
    enqueue(application_id)
    db = SessionLocal()
    try:
        jobs = list(QueueJobRepository(db).list_by_application(application_id))
        jobs[0].status = JobStatus.COMPLETED
        jobs[1].status = JobStatus.FAILED
        db.commit()
    finally:
        db.close()
    response = client.post(f"{API}/applications/{application_id}/processing/retry")
    assert response.status_code == 200
    assert response.json()["documents_retried"] == 1
    counts = queue_counts(application_id)
    assert counts.get(JobStatus.COMPLETED, 0) == 1
    assert counts.get(JobStatus.FAILED, 0) == 0


def test_progress_endpoint_counts_statuses(client):
    authenticate(client)
    application_id, _ = create_application_with_documents(4)
    enqueue(application_id)
    db = SessionLocal()
    try:
        jobs = list(QueueJobRepository(db).list_by_application(application_id))
        jobs[0].status = JobStatus.PROCESSING
        jobs[1].status = JobStatus.COMPLETED
        jobs[2].status = JobStatus.FAILED
        jobs[3].status = JobStatus.RETRY_WAITING
        db.commit()
    finally:
        db.close()

    response = client.get(f"{API}/applications/{application_id}/queue/progress")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "application_id": application_id,
        "total": 4,
        "queued": 0,
        "processing": 1,
        "completed": 1,
        "failed": 1,
        "retry_waiting": 1,
    }


def test_queue_stats_endpoint_is_system_wide(client):
    """/queue/stats aggregates across every application, not just one."""
    authenticate(client)
    application_id, _ = create_application_with_documents(4)
    enqueue(application_id)
    db = SessionLocal()
    try:
        jobs = list(QueueJobRepository(db).list_by_application(application_id))
        jobs[0].status = JobStatus.PROCESSING
        jobs[1].status = JobStatus.COMPLETED
        jobs[2].status = JobStatus.FAILED
        jobs[3].status = JobStatus.QUEUED
        jobs[3].created_at = datetime.now(timezone.utc) - timedelta(seconds=120)
        db.commit()
    finally:
        db.close()

    other_application_id, _ = create_application_with_documents(1)
    enqueue(other_application_id)

    response = client.get(f"{API}/queue/stats")

    assert response.status_code == 200, response.text
    data = response.json()
    # jobs[3] (backdated) plus the other application's freshly enqueued job.
    assert data["total_queued"] == 2
    assert data["total_processing"] == 1
    assert data["total_failed"] == 1
    assert data["oldest_queued_age_seconds"] >= 120


def test_queue_stats_endpoint_empty_queue(client):
    """An empty queue reports zero counts and no oldest-queued age."""
    authenticate(client)
    response = client.get(f"{API}/queue/stats")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "total_queued": 0,
        "total_processing": 0,
        "total_failed": 0,
        "oldest_queued_age_seconds": None,
    }


def test_two_workers_cannot_claim_same_job():
    application_id, _ = create_application_with_documents(2)
    enqueue(application_id)
    db_one = SessionLocal()
    db_two = SessionLocal()
    try:
        first = QueueJobRepository(db_one).claim_next(worker_id="worker-a")
        second = QueueJobRepository(db_two).claim_next(worker_id="worker-b")
        assert first is not None
        assert second is not None
        assert first.id != second.id
    finally:
        db_one.close()
        db_two.close()


def test_successful_worker_processing_marks_job_completed():
    application_id, document_ids = create_application_with_documents(1)
    enqueue(application_id)

    summary = BulkQueueWorker(processor_factory=SuccessfulProcessor).run_until_empty()

    assert summary.succeeded == 1
    counts = queue_counts(application_id)
    assert counts[JobStatus.COMPLETED] == 1
    db = SessionLocal()
    try:
        assert db.get(Document, document_ids[0]).processing_status is DocumentProcessingStatus.COMPLETED
    finally:
        db.close()


def test_failed_processing_retries_then_permanently_fails(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 2)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 0)
    application_id, _ = create_application_with_documents(1)
    enqueue(application_id)
    worker = BulkQueueWorker(settings=settings, processor_factory=FailingProcessor)

    first = worker.run_until_empty(max_jobs=1)
    second = worker.run_until_empty(max_jobs=1)

    assert first.retried == 1
    assert second.failed == 1
    counts = queue_counts(application_id)
    assert counts[JobStatus.FAILED] == 1


def test_stale_processing_job_recovery():
    application_id, _ = create_application_with_documents(1)
    enqueue(application_id)
    db = SessionLocal()
    try:
        job = QueueJobRepository(db).claim_next(worker_id="lost-worker")
        assert job is not None
        job.started_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        recovered = QueueJobRepository(db).recover_stale_processing(stale_after_seconds=10)
        db.refresh(job)
        assert recovered == 1
        assert job.status is JobStatus.QUEUED
        assert job.worker_id is None
    finally:
        db.close()


def test_empty_queue_worker_returns_zero():
    summary = BulkQueueWorker(processor_factory=SuccessfulProcessor).run_until_empty()

    assert summary.processed == 0


def test_80_document_batch_simulation_and_configurable_concurrency(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_workers", 3)
    application_id, _ = create_application_with_documents(80)
    enqueue(application_id)
    SleepingProcessor.active = 0
    SleepingProcessor.max_active = 0

    started = time.perf_counter()
    summary = drain_queue(settings=settings, processor_factory=SleepingProcessor)
    elapsed = time.perf_counter() - started
    docs_per_minute = summary.succeeded / (elapsed / 60)

    assert summary.succeeded == 80
    assert queue_counts(application_id)[JobStatus.COMPLETED] == 80
    assert SleepingProcessor.max_active <= 3
    assert SleepingProcessor.max_active >= 2
    assert docs_per_minute > 0


@pytest.mark.parametrize("workers", [1, 2, 3])
def test_worker_concurrency_benchmark(workers):
    application_id, _ = create_application_with_documents(12)
    enqueue(application_id)
    SleepingProcessor.active = 0
    SleepingProcessor.max_active = 0

    started = time.perf_counter()
    summary = drain_queue(workers=workers, processor_factory=SleepingProcessor)
    elapsed = time.perf_counter() - started

    assert summary.succeeded == 12
    assert SleepingProcessor.max_active <= workers
    assert elapsed > 0


def test_completed_application_reports_full_progress(client):
    authenticate(client)
    application_id, _ = create_application_with_documents(5)
    enqueue(application_id)
    db = SessionLocal()
    try:
        jobs = list(QueueJobRepository(db).list_by_application(application_id))
        for job in jobs:
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    response = client.get(f"{API}/applications/{application_id}/processing/progress")
    assert response.status_code == 200
    assert response.json() == {
        "application_id": application_id,
        "total_documents": 5,
        "queued": 0,
        "processing": 0,
        "completed": 5,
        "failed": 0,
        "progress_percentage": 100.0,
        "documents_needing_attention": 0,
    }


class MixedProcessor:
    """Processor that succeeds for even-indexed docs, fails for odd-indexed."""

    def __init__(self, db):
        self._db = db

    def process_one(self, *, application_id: int, document_id: int):
        document = self._db.get(Document, document_id)
        index = document.copy_number - 1
        if index % 2 == 0:
            document.processing_status = DocumentProcessingStatus.COMPLETED
            self._db.add(document)
            self._db.commit()
            return DocumentProcessingResult(
                document_id=document_id,
                file_name=document.original_filename,
                outcome=ProcessingOutcome.PROCESSED,
            )
        raise RuntimeError("transient failure")


def test_mixed_success_failure_retry_requeues_only_failed(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 1)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 0)

    authenticate(client)
    application_id, document_ids = create_application_with_documents(4)
    enqueue(application_id)

    worker = BulkQueueWorker(settings=settings, processor_factory=MixedProcessor)
    worker.run_until_empty()

    counts = queue_counts(application_id)
    assert counts[JobStatus.COMPLETED] == 2
    assert counts[JobStatus.FAILED] == 2

    db = SessionLocal()
    try:
        retried = QueueJobRepository(db).retry_failed_for_application(application_id)
        assert retried == 2
        # Already-completed documents must not be requeued: no new job rows
        # and the completed jobs keep their status.
        jobs_after_retry = list(QueueJobRepository(db).list_by_application(application_id))
        assert len(jobs_after_retry) == 4
        assert sum(job.status is JobStatus.COMPLETED for job in jobs_after_retry) == 2
    finally:
        db.close()

    worker2 = BulkQueueWorker(settings=settings, processor_factory=MixedProcessor)
    worker2.run_until_empty()

    counts_after = queue_counts(application_id)
    assert counts_after[JobStatus.COMPLETED] == 2
    assert counts_after[JobStatus.FAILED] == 2


@pytest.mark.parametrize("method,endpoint", [
    ("post", "/applications/1/processing/start"),
    ("get", "/applications/1/processing/progress"),
    ("get", "/applications/1/processing/documents"),
    ("post", "/applications/1/processing/retry"),
    ("post", "/applications/1/queue/enqueue"),
    ("get", "/applications/1/queue/progress"),
    ("get", "/queue/stats"),
    ("post", "/queue/workers/drain"),
])
def test_unauthenticated_requests_rejected(client, method, endpoint):
    func = getattr(client, method)
    response = func(f"{API}{endpoint}")
    assert response.status_code == 401, f"{method.upper()} {endpoint} -> {response.status_code}"


def test_stale_processing_job_exhausted_attempts_becomes_failed():
    """A stale job that already exhausted its attempts fails permanently."""
    application_id, document_ids = create_application_with_documents(1)
    enqueue(application_id)
    db = SessionLocal()
    try:
        job = QueueJobRepository(db).claim_next(worker_id="lost-worker")
        assert job is not None
        job.attempts = job.max_attempts
        job.started_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        recovered = QueueJobRepository(db).recover_stale_processing(stale_after_seconds=10)
        db.refresh(job)
        assert recovered == 1
        assert job.status is JobStatus.FAILED
        assert job.worker_id is None
        assert job.started_at is None
        assert (
            db.get(Document, document_ids[0]).processing_status
            is DocumentProcessingStatus.FAILED
        )
    finally:
        db.close()


def test_recovered_stale_job_is_processed_again_to_completion():
    """A recovered stale job is claimed and completed; nothing stays stuck."""
    application_id, _ = create_application_with_documents(1)
    enqueue(application_id)
    db = SessionLocal()
    try:
        job = QueueJobRepository(db).claim_next(worker_id="lost-worker")
        assert job is not None
        job.started_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
    finally:
        db.close()

    summary = BulkQueueWorker(processor_factory=SuccessfulProcessor).run_until_empty()

    assert summary.succeeded == 1
    counts = queue_counts(application_id)
    assert counts[JobStatus.COMPLETED] == 1
    assert counts.get(JobStatus.PROCESSING, 0) == 0


def test_recovered_stale_job_resets_document_status():
    """Recovery never leaves a document stuck in PROCESSING."""
    application_id, document_ids = create_application_with_documents(1)
    enqueue(application_id)
    db = SessionLocal()
    try:
        job = QueueJobRepository(db).claim_next(worker_id="lost-worker")
        assert job.document.processing_status is DocumentProcessingStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        QueueJobRepository(db).recover_stale_processing(stale_after_seconds=10)
        db.refresh(job)
        assert job.status is JobStatus.QUEUED
        assert (
            db.get(Document, document_ids[0]).processing_status
            is DocumentProcessingStatus.UPLOADED
        )
    finally:
        db.close()


def test_retry_exhaustion_records_error_and_fails_document(monkeypatch):
    """Retry exhaustion stores the last error and fails the document."""
    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 2)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 0)
    application_id, document_ids = create_application_with_documents(1)
    enqueue(application_id)
    worker = BulkQueueWorker(settings=settings, processor_factory=FailingProcessor)

    worker.run_until_empty(max_jobs=1)
    worker.run_until_empty(max_jobs=1)

    db = SessionLocal()
    try:
        job = list(QueueJobRepository(db).list_by_application(application_id))[0]
        assert job.status is JobStatus.FAILED
        assert job.last_error == "transient failure"
        assert (
            db.get(Document, document_ids[0]).processing_status
            is DocumentProcessingStatus.FAILED
        )
    finally:
        db.close()


def test_exponential_backoff_schedules_growing_retry_at(monkeypatch):
    """Retry deadlines grow exponentially: 1x, 2x, 4x of the base backoff."""
    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_max_attempts", 3)
    monkeypatch.setattr(settings, "bulk_queue_retry_backoff_seconds", 10)
    application_id, _ = create_application_with_documents(1)
    enqueue(application_id)
    worker = BulkQueueWorker(settings=settings, processor_factory=FailingProcessor)

    delays: list[float] = []
    for _ in range(3):
        started = time.time()
        summary = worker.run_until_empty(max_jobs=1)
        assert summary.processed == 1
        db = SessionLocal()
        try:
            job = list(QueueJobRepository(db).list_by_application(application_id))[0]
            if job.status is JobStatus.RETRY_WAITING:
                delays.append(job.retry_at.timestamp() - started)
                # Simulate time passing so the next attempt may claim the job.
                job.retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                db.commit()
            else:
                assert job.status is JobStatus.FAILED
        finally:
            db.close()

    assert delays == pytest.approx([10, 20], abs=1.5)


def test_completed_jobs_never_reprocessed():
    """Completed jobs are never claimed or reprocessed by workers."""
    application_id, _ = create_application_with_documents(2)
    enqueue(application_id)
    db = SessionLocal()
    try:
        jobs = list(QueueJobRepository(db).list_by_application(application_id))
        for job in jobs:
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
        db.commit()
        assert QueueJobRepository(db).claim_next(worker_id="probe") is None
    finally:
        db.close()

    summary = BulkQueueWorker(processor_factory=SuccessfulProcessor).run_until_empty()

    assert summary.processed == 0
    counts = queue_counts(application_id)
    assert counts[JobStatus.COMPLETED] == 2


def test_completed_documents_never_requeued(client):
    """Enqueueing again after completion creates no duplicate jobs."""
    authenticate(client)
    application_id, _ = create_application_with_documents(2)
    enqueue(application_id)
    db = SessionLocal()
    try:
        jobs = list(QueueJobRepository(db).list_by_application(application_id))
        for job in jobs:
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            job.document.processing_status = DocumentProcessingStatus.COMPLETED
        db.commit()
    finally:
        db.close()

    response = client.post(f"{API}/applications/{application_id}/queue/enqueue")

    assert response.status_code == 200, response.text
    assert response.json()["jobs_created"] == 0
    counts = queue_counts(application_id)
    assert counts[JobStatus.COMPLETED] == 2


def test_heartbeat_refreshes_started_at_preventing_false_stale(monkeypatch):
    """A live but slow worker is never falsely declared stale and reprocessed."""
    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_stale_after_seconds", 3)
    application_id, _ = create_application_with_documents(1)
    enqueue(application_id)

    class SlowProcessor:
        """Processor that works longer than the stale timeout."""

        def __init__(self, db):
            self._db = db

        def process_one(self, *, application_id: int, document_id: int):
            time.sleep(3.2)
            document = self._db.get(Document, document_id)
            document.processing_status = DocumentProcessingStatus.COMPLETED
            self._db.add(document)
            self._db.commit()
            return DocumentProcessingResult(
                document_id=document_id,
                file_name="slow.pdf",
                outcome=ProcessingOutcome.PROCESSED,
            )

    worker = BulkQueueWorker(settings=settings, processor_factory=SlowProcessor)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(worker.run_until_empty, max_jobs=1)
        time.sleep(0.6)  # let the worker claim the job and start processing

        db = SessionLocal()
        try:
            job = list(QueueJobRepository(db).list_by_application(application_id))[0]
            assert job.status is JobStatus.PROCESSING
            claimed_at = job.started_at
            # Another worker polls while the first is still processing; the
            # heartbeat must keep the lease fresh.
            assert QueueJobRepository(db).recover_stale_processing(stale_after_seconds=3) == 0
            time.sleep(1.5)
            assert QueueJobRepository(db).recover_stale_processing(stale_after_seconds=3) == 0
            db.refresh(job)
            assert job.started_at > claimed_at  # heartbeat refreshed the lease
            assert job.status is JobStatus.PROCESSING
        finally:
            db.close()

        summary = future.result(timeout=30)

    assert summary.succeeded == 1
    counts = queue_counts(application_id)
    assert counts[JobStatus.COMPLETED] == 1


def test_loop_forever_polls_until_stopped(monkeypatch, tmp_path):
    """loop_forever drains jobs and exits gracefully when stopped."""
    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_queue_poll_interval", 0.05)
    monkeypatch.setattr(settings, "worker_heartbeat_path", tmp_path / "worker.heartbeat")
    application_id, _ = create_application_with_documents(2)
    enqueue(application_id)
    worker = BulkQueueWorker(settings=settings, processor_factory=SuccessfulProcessor)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(worker.loop_forever)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            counts = queue_counts(application_id)
            if counts.get(JobStatus.COMPLETED, 0) == 2:
                break
            time.sleep(0.05)
        worker.stop()
        future.result(timeout=10)

    counts = queue_counts(application_id)
    assert counts[JobStatus.COMPLETED] == 2
    heartbeat_path = settings.worker_heartbeat_path
    assert heartbeat_path.exists()
    assert time.time() - float(heartbeat_path.read_text()) < 5


def test_large_batch_progress_counts_consistent(client):
    """Progress stays consistent after a 40-document batch completes."""
    authenticate(client)
    application_id, _ = create_application_with_documents(40)
    enqueue(application_id)

    summary = BulkQueueWorker(processor_factory=SuccessfulProcessor).run_until_empty()
    assert summary.succeeded == 40

    response = client.get(f"{API}/applications/{application_id}/processing/progress")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_documents"] == 40
    assert data["completed"] == 40
    assert data["failed"] == 0
    assert data["queued"] == 0
    assert data["processing"] == 0
    assert data["progress_percentage"] == 100.0
    assert data["documents_needing_attention"] == 0


def test_multiple_worker_processes_claim_disjoint_jobs(tmp_path):
    """Three OS-level worker processes claim disjoint jobs (no duplicates)."""
    application_id, document_ids = create_application_with_documents(12)
    enqueue(application_id)
    record_dir = tmp_path / "claims"
    record_dir.mkdir()

    import sys
    context_method = "fork" if sys.platform != "win32" else "spawn"
    context = multiprocessing.get_context(context_method)
    processes = [
        context.Process(target=_drain_in_child_process, args=(str(record_dir),))
        for _ in range(3)
    ]
    for process in processes:
        process.start()
    for process in processes:
        # Windows has no fork(); each child re-imports the whole app (incl.
        # PaddleOCR) via spawn from scratch, which is slow and gets slower
        # still competing for CPU with the rest of the full suite -- 120s was
        # occasionally too tight under full-suite load even though the child
        # work itself finishes in seconds when run alone.
        process.join(timeout=240)
    assert all(process.exitcode == 0 for process in processes), [
        process.exitcode for process in processes
    ]

    # `FOR UPDATE SKIP LOCKED` has an inherent last-row race: when only one
    # or two rows remain, a worker's claim can land in the razor-thin window
    # between another worker's SELECT and its COMMIT, so `claim_next` returns
    # None for a row that is about to free up rather than one that is truly
    # gone -- the row is never lost (it stays QUEUED for the next poll, exactly
    # as it would in production's `loop_forever`), but three one-shot workers
    # can rarely stop a hair before the queue is empty. Mirror that next poll
    # here so the disjoint-claims assertion below is deterministic.
    global _record_dir
    _record_dir = str(record_dir)
    BulkQueueWorker(processor_factory=RecordProcessor).run_until_empty()

    claimed = [
        int(line)
        for record_file in record_dir.iterdir()
        for line in record_file.read_text(encoding="utf-8").splitlines()
    ]
    assert len(claimed) == 12
    assert len(set(claimed)) == 12
    assert set(claimed) == set(document_ids)

    counts = queue_counts(application_id)
    assert counts[JobStatus.COMPLETED] == 12
    assert counts.get(JobStatus.PROCESSING, 0) == 0
    assert counts.get(JobStatus.QUEUED, 0) == 0


def test_bulk_upload_split_documents_are_enqueued_for_processing(client):
    """Regression test: the queue worker's bulk-split path used to call a
    nonexistent `QueueJobRepository.enqueue()`. The split itself succeeded
    (documents were created) but the resulting per-document jobs were never
    created, silently stalling every real bulk upload after the split with
    no error surfaced anywhere -- a live application hit this in production
    use before it was caught. Exercises the real `DocumentProcessingService`
    (not a fake processor) so this path is actually covered.
    """
    authenticate(client)
    application_id = create_application(client)
    response = upload_bulk(
        client,
        application_id,
        make_bulk_pdf([
            "TRIPARTITE AGREEMENT\nFirst copy.",
            "TRIPARTITE AGREEMENT\nSecond copy.",
        ]),
    )
    assert response.status_code == 201, response.text

    def processor_factory(db):
        # No real OCR engine needed: the test PDF carries embedded text, so
        # the splitter classifies pages from that directly.
        return DocumentProcessingService(db, engine_factory=lambda: None)

    summary = BulkQueueWorker(processor_factory=processor_factory).run_until_empty()
    assert summary.failed == 0, summary

    db = SessionLocal()
    try:
        documents = (
            db.query(Document)
            .filter(Document.application_id == application_id)
            .all()
        )
        split_documents = [d for d in documents if d.document_type != DocumentType.BULK_UPLOAD]
        assert len(split_documents) == 2

        jobs = (
            db.query(QueueJob)
            .filter(QueueJob.document_id.in_([d.id for d in split_documents]))
            .all()
        )
        assert len(jobs) == 2
        assert {job.document_id for job in jobs} == {d.id for d in split_documents}
    finally:
        db.close()


def test_bulk_upload_ocr_fallback_splits_watermark_only_scans(client):
    """Regression test for the real-data bug found 2026-08-15: a page whose
    only *native* text is a short scanner-app watermark (e.g. CamScanner,
    exactly 10 characters) must still trigger OCR during splitting, not be
    read as if the watermark were the page's entire content.

    Before the fix, the OCR-fallback threshold was a flat `< 10`, so a page
    with exactly 10 characters of native text never triggered OCR. Every
    page of a real scanned bulk PDF then read as just its watermark, matched
    no title phrase, and the whole file collapsed into one
    OTHER_SUPPORTING_DOCUMENT instead of splitting -- confirmed directly on
    real files in Confidential Data/ (12 of 21 hit this exact bug).
    """
    authenticate(client)
    application_id = create_application(client)

    # Mirrors a real CamScanner export: each page's only native text is a
    # short watermark, well under any real document's actual content length.
    watermark_doc = pymupdf.open()
    for _ in range(2):
        page = watermark_doc.new_page()
        page.insert_text((50, 50), "CamScanner", fontsize=10)
    content = watermark_doc.tobytes()
    watermark_doc.close()

    response = upload_bulk(client, application_id, content)
    assert response.status_code == 201, response.text

    # The splitter can only "see" real content via this fake engine's OCR
    # fallback -- there is no other source of classifiable text on these
    # pages, so a correct split proves the fallback actually ran.
    ocr_engine = FakeOCREngine(
        texts=[
            "TRIPARTITE AGREEMENT\nFirst copy body text.",
            "AUTHORITY LETTER\nSecond copy body text.",
        ]
    )

    def processor_factory(db):
        return DocumentProcessingService(db, engine_factory=lambda: ocr_engine)

    summary = BulkQueueWorker(processor_factory=processor_factory).run_until_empty()
    assert summary.failed == 0, summary

    db = SessionLocal()
    try:
        documents = (
            db.query(Document)
            .filter(Document.application_id == application_id)
            .all()
        )
        split_documents = [d for d in documents if d.document_type != DocumentType.BULK_UPLOAD]
        assert len(split_documents) == 2
        assert {d.document_type for d in split_documents} == {
            DocumentType.TRIPARTITE_AGREEMENT,
            DocumentType.AUTHORITY_LETTER,
        }
    finally:
        db.close()
