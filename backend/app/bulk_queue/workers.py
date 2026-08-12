"""Controlled workers for the persistent bulk processing queue."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.database.connection import SessionLocal
from app.database.models.enums import JobStatus
from app.database.models.queue_job import QueueJob
from app.database.repositories.queue_job_repository import QueueJobRepository
from app.document_processing.schemas import ProcessingOutcome
from app.document_processing.services import DocumentProcessingService

logger = logging.getLogger(__name__)


@dataclass
class WorkerRunSummary:
    """Aggregate result of draining the queue."""

    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    retried: int = 0


class BulkQueueWorker:
    """Claims and processes jobs one at a time."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] = SessionLocal,
        settings: Settings | None = None,
        worker_id: str | None = None,
        processor_factory: Callable[[Session], DocumentProcessingService] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings or get_settings()
        self.worker_id = worker_id or f"bulk-worker-{uuid.uuid4()}"
        self._processor_factory = processor_factory or DocumentProcessingService
        self._stop_requested = False

    def stop(self) -> None:
        """Request graceful shutdown after the current job."""
        self._stop_requested = True

    def run_until_empty(self, *, max_jobs: int | None = None) -> WorkerRunSummary:
        """Drain available jobs until empty, stopped, or max_jobs is reached."""
        summary = WorkerRunSummary()
        while not self._stop_requested and (max_jobs is None or summary.processed < max_jobs):
            with self._session_factory() as db:
                jobs = QueueJobRepository(db)
                jobs.recover_stale_processing(
                    stale_after_seconds=self._settings.bulk_queue_stale_after_seconds
                )
                job = jobs.claim_next(worker_id=self.worker_id)
                if job is None:
                    break
                self._process_claimed_job(db, jobs, job, summary)
        return summary

    def loop_forever(self) -> None:
        """Continuously poll for jobs until :meth:`stop` is called."""
        while not self._stop_requested:
            summary = self.run_until_empty(max_jobs=1)
            if summary.processed == 0:
                time.sleep(self._settings.bulk_queue_poll_interval)

    def _process_claimed_job(
        self,
        db: Session,
        jobs: QueueJobRepository,
        job: QueueJob,
        summary: WorkerRunSummary,
    ) -> None:
        summary.processed += 1
        try:
            result = self._processor_factory(db).process_one(
                application_id=job.application_id,
                document_id=job.document_id,
            )
            if result.outcome is ProcessingOutcome.FAILED:
                raise RuntimeError(result.message or "Document processing failed")
            if result.outcome is ProcessingOutcome.SKIPPED:
                raise RuntimeError(result.message or "Document skipped")
            jobs.mark_completed(job)
            summary.succeeded += 1
            logger.info(
                "Bulk queue job completed job_id=%s document_id=%s worker_id=%s",
                job.id,
                job.document_id,
                self.worker_id,
            )
        except Exception as exc:
            logger.exception(
                "Bulk queue job failed job_id=%s document_id=%s worker_id=%s",
                job.id,
                job.document_id,
                self.worker_id,
            )
            updated = jobs.mark_failed_attempt(
                job,
                error=str(exc) or exc.__class__.__name__,
                retry_backoff_seconds=self._settings.bulk_queue_retry_backoff_seconds,
            )
            if updated.status is JobStatus.FAILED:
                summary.failed += 1
            else:
                summary.retried += 1


def drain_queue(
    *,
    workers: int | None = None,
    session_factory: sessionmaker[Session] = SessionLocal,
    settings: Settings | None = None,
    processor_factory: Callable[[Session], DocumentProcessingService] | None = None,
) -> WorkerRunSummary:
    """Drain available queue jobs with controlled worker count.

    The synchronous implementation advances workers round-robin. Production can
    run separate processes with the same worker class; PostgreSQL row locks still
    guarantee distinct claims.
    """
    resolved_settings = settings or get_settings()
    worker_count = workers or resolved_settings.bulk_queue_workers
    queue_workers = [
        BulkQueueWorker(
            session_factory=session_factory,
            settings=resolved_settings,
            processor_factory=processor_factory,
        )
        for _ in range(worker_count)
    ]
    aggregate = WorkerRunSummary()
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        for summary in executor.map(lambda worker: worker.run_until_empty(), queue_workers):
            aggregate.processed += summary.processed
            aggregate.succeeded += summary.succeeded
            aggregate.failed += summary.failed
            aggregate.retried += summary.retried
    return aggregate
