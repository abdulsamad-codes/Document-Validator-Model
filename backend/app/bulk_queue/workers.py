"""Controlled workers for the persistent bulk processing queue.

Two deployment modes are supported:

* **In-process (development).** ``drain_queue`` runs a bounded pool of worker
  threads inside the API process, driven by FastAPI ``BackgroundTasks``. This
  keeps the operator flow convenient while the queue remains PostgreSQL-backed.
  Set ``bulk_queue_background_drain=false`` to disable this mode.

* **Dedicated worker processes (production).** Run ``python -m app.bulk_queue``
  as one or more separate processes; each runs :meth:`BulkQueueWorker.loop_forever`
  and polls the same PostgreSQL queue. Row-level ``FOR UPDATE SKIP LOCKED``
  claiming guarantees two workers — in the same process or in different
  processes — can never claim the same job.

Workers refresh a per-job heartbeat while processing so that a slow but live
worker is never falsely declared crashed, while jobs abandoned by a crashed
worker are recovered by the next poll after ``bulk_queue_stale_after_seconds``.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.bulk_queue.pipeline_runner import PipelineRunnerService
from app.core.config import Settings, get_settings
from app.database.connection import SessionLocal
from app.database.models.enums import ApplicationStatus, JobStatus, JobType
from app.database.models.queue_job import QueueJob
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.audit_log_repository import AuditLogRepository
from app.database.repositories.queue_job_repository import QueueJobRepository
from app.document_processing.schemas import ProcessingOutcome
from app.document_processing.services import DocumentProcessingService

logger = logging.getLogger(__name__)

#: Audit action recorded when every document job for an application is
#: terminal but none succeeded, so the pipeline job is deliberately never
#: enqueued -- see PIPELINE_BLOCKED handling in _maybe_start_pipeline.
ACTION_PIPELINE_BLOCKED = "PIPELINE_BLOCKED_NO_PROCESSED_DOCUMENTS"


@dataclass
class WorkerRunSummary:
    """Aggregate result of draining the queue."""

    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    retried: int = 0


class BulkQueueWorker:
    """Claims and processes jobs one at a time.

    Args:
        session_factory: Factory producing one session per claim/heartbeat.
            Defaults to the application's :data:`SessionLocal`.
        settings: Application settings; defaults to the cached process settings.
        worker_id: Stable identifier stored on claimed jobs. Auto-generated when
            omitted.
        processor_factory: Callable receiving a session and returning the object
            with a ``process_one(application_id=..., document_id=...)`` method.
            Defaults to the real :class:`DocumentProcessingService`.
        pipeline_runner_factory: Callable receiving a session and returning the
            object with a ``run(application_id=...)`` method. Defaults to the
            real :class:`PipelineRunnerService`.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] = SessionLocal,
        settings: Settings | None = None,
        worker_id: str | None = None,
        processor_factory: Callable[[Session], DocumentProcessingService] | None = None,
        pipeline_runner_factory: Callable[[Session], PipelineRunnerService] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings or get_settings()
        self.worker_id = worker_id or f"bulk-worker-{uuid.uuid4()}"
        self._processor_factory = processor_factory or DocumentProcessingService
        self._pipeline_runner_factory = pipeline_runner_factory or PipelineRunnerService
        self._stop_requested = False

    def stop(self) -> None:
        """Request graceful shutdown after the current job."""
        self._stop_requested = True

    def run_until_empty(self, *, max_jobs: int | None = None) -> WorkerRunSummary:
        """Drain available jobs until empty, stopped, or max_jobs is reached.

        Stale PROCESSING jobs abandoned by crashed workers are recovered before
        every claim attempt, so recovery requires no manual intervention and no
        job is permanently stuck in PROCESSING as long as at least one worker is
        alive.

        Args:
            max_jobs: Optional cap on the number of jobs processed by this run.

        Returns:
            The aggregate outcome of the run.
        """
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
        """Continuously poll for jobs until :meth:`stop` is called.

        Intended for dedicated worker processes (``python -m app.bulk_queue``).
        Each iteration drains one job, then sleeps ``bulk_queue_poll_interval``
        seconds when the queue is empty.
        """
        while not self._stop_requested:
            summary = self.run_until_empty(max_jobs=1)
            if summary.processed == 0:
                time.sleep(self._settings.bulk_queue_poll_interval)

    def _heartbeat_interval(self) -> float:
        """Seconds between heartbeat refreshes, derived from the stale timeout.

        A live worker must refresh ``started_at`` well before the stale timeout
        fires; one third of the timeout (minimum one second) keeps the heartbeat
        cheap while leaving generous headroom for slow OCR runs.
        """
        stale_after = self._settings.bulk_queue_stale_after_seconds
        if stale_after <= 0:
            return 0.0
        return max(1, stale_after // 3)

    def _start_heartbeat(self, job_id: int) -> Callable[[], None]:
        """Start a daemon heartbeat thread for a claimed job.

        The thread refreshes the job's ``started_at`` lease every heartbeat
        interval using its own session, so a long-running but live worker is not
        declared stale (and its document is not reprocessed by another worker).
        The returned callable stops and joins the thread.

        Args:
            job_id: Id of the claimed job.

        Returns:
            A stop function for the heartbeat thread.
        """
        interval = self._heartbeat_interval()
        if interval <= 0:
            return lambda: None

        stop_event = threading.Event()

        def _beat() -> None:
            while not stop_event.wait(interval):
                try:
                    with self._session_factory() as heartbeat_db:
                        QueueJobRepository(heartbeat_db).heartbeat(job_id=job_id)
                except Exception:
                    logger.exception(
                        "Bulk queue heartbeat failed for job_id=%s worker_id=%s",
                        job_id,
                        self.worker_id,
                    )

        thread = threading.Thread(
            target=_beat,
            name=f"bulk-heartbeat-{self.worker_id}-{job_id}",
            daemon=True,
        )
        thread.start()

        def _stop() -> None:
            stop_event.set()
            thread.join(timeout=interval + 2)

        return _stop

    def _process_claimed_job(
        self,
        db: Session,
        jobs: QueueJobRepository,
        job: QueueJob,
        summary: WorkerRunSummary,
    ) -> None:
        summary.processed += 1
        stop_heartbeat = self._start_heartbeat(job.id)
        try:
            try:
                if job.job_type is JobType.APPLICATION_PIPELINE:
                    self._pipeline_runner_factory(db).run(application_id=job.application_id)
                else:
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
                    "Bulk queue job completed job_id=%s job_type=%s document_id=%s worker_id=%s",
                    job.id,
                    job.job_type.value,
                    job.document_id,
                    self.worker_id,
                )
            except Exception as exc:
                logger.exception(
                    "Bulk queue job failed job_id=%s job_type=%s document_id=%s worker_id=%s",
                    job.id,
                    job.job_type.value,
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

            # Outside the try/except above on purpose: this decides whether to
            # start the *next* stage, not whether *this* job succeeded, so a
            # problem here must never be mistaken for this job's own outcome
            # (which would wrongly mark a just-completed document job failed).
            if job.job_type is JobType.DOCUMENT_OCR and job.status in (
                JobStatus.COMPLETED,
                JobStatus.FAILED,
            ):
                self._maybe_start_pipeline(db, jobs, job.application_id)
        finally:
            stop_heartbeat()

    def _maybe_start_pipeline(
        self,
        db: Session,
        jobs: QueueJobRepository,
        application_id: int,
    ) -> None:
        """Enqueue the pipeline job once every document job is terminal.

        Called after a ``DOCUMENT_OCR`` job reaches COMPLETED or (permanent)
        FAILED. Cheap no-op otherwise-terminal-jobs-remain check first, so this
        only does real work exactly once per application's document batch. Safe
        under concurrent workers -- see ``try_enqueue_pipeline_job``.
        """
        if not jobs.all_document_jobs_terminal(application_id):
            return
        if not jobs.any_document_job_completed(application_id):
            logger.warning(
                "Pipeline not started for application id=%s: no documents were "
                "successfully processed",
                application_id,
            )
            AuditLogRepository(db).create(
                application_id=application_id,
                username="system",
                action=ACTION_PIPELINE_BLOCKED,
                details={"reason": "All document jobs finished with zero successes"},
            )
            applications = ApplicationRepository(db)
            application = applications.get_by_id(application_id)
            if application is not None and application.status is ApplicationStatus.PROCESSING:
                applications.update(application, status=ApplicationStatus.PROCESSING_FAILED)
            db.commit()
            return
        enqueued = jobs.try_enqueue_pipeline_job(
            application_id=application_id,
            max_attempts=self._settings.bulk_queue_max_attempts,
        )
        if enqueued is not None:
            logger.info("Pipeline job enqueued for application id=%s", application_id)


def drain_queue(
    *,
    workers: int | None = None,
    session_factory: sessionmaker[Session] = SessionLocal,
    settings: Settings | None = None,
    processor_factory: Callable[[Session], DocumentProcessingService] | None = None,
) -> WorkerRunSummary:
    """Drain available queue jobs with controlled worker count.

    The synchronous implementation advances workers round-robin in a thread
    pool. Production can run separate processes with the same worker class;
    PostgreSQL row locks still guarantee distinct claims.

    Args:
        workers: Number of concurrent workers; defaults to the configured
            ``bulk_queue_workers``.
        session_factory: Session factory handed to every worker.
        settings: Application settings; defaults to the cached process settings.
        processor_factory: Processor factory handed to every worker; defaults to
            the real document processing service.

    Returns:
        The aggregate outcome across all workers.
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
