"""Tests for the persistent bulk processing queue."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from threading import Lock

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
    assert counts[JobStatus.COMPLETED] == 1
    assert counts[JobStatus.QUEUED] == 1


def test_progress_endpoint_counts_statuses(client):
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
