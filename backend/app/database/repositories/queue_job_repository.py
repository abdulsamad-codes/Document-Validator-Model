"""Repository for the PostgreSQL-backed queue job table."""

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from app.database.models.document import Document
from app.database.models.enums import DocumentProcessingStatus, JobStatus
from app.database.models.queue_job import QueueJob
from app.database.repositories.base import BaseRepository


class QueueJobRepository(BaseRepository[QueueJob]):
    """Persistence operations for queue jobs."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[QueueJob]:
        return QueueJob

    def enqueue_uploaded_documents(
        self,
        *,
        application_id: int,
        max_attempts: int,
    ) -> tuple[list[QueueJob], int, int]:
        """Create jobs for eligible uploaded documents without duplicating jobs."""
        document_ids = self._db.scalars(
            select(Document.id).where(
                Document.application_id == application_id,
                Document.processing_status == DocumentProcessingStatus.UPLOADED,
            )
        ).all()
        if not document_ids:
            return [], 0, 0

        existing_ids = set(
            self._db.scalars(
                select(QueueJob.document_id).where(QueueJob.document_id.in_(document_ids))
            ).all()
        )
        missing_ids = [document_id for document_id in document_ids if document_id not in existing_ids]

        if missing_ids:
            if self._db.bind and self._db.bind.dialect.name == "postgresql":
                rows = [
                    {
                        "application_id": application_id,
                        "document_id": document_id,
                        "status": JobStatus.QUEUED,
                        "max_attempts": max_attempts,
                    }
                    for document_id in missing_ids
                ]
                statement = pg_insert(QueueJob).values(rows).on_conflict_do_nothing(
                    index_elements=["document_id"]
                )
                self._db.execute(statement)
            else:
                for document_id in missing_ids:
                    self._db.add(
                        QueueJob(
                            application_id=application_id,
                            document_id=document_id,
                            max_attempts=max_attempts,
                        )
                    )
            self._db.commit()

        jobs = list(
            self._db.scalars(
                select(QueueJob)
                .where(QueueJob.document_id.in_(document_ids))
                .order_by(QueueJob.id)
            ).all()
        )
        created = sum(1 for job in jobs if job.document_id in set(missing_ids))
        return jobs, created, len(document_ids) - created

    def claim_next(
        self,
        *,
        worker_id: str,
        now: datetime | None = None,
    ) -> QueueJob | None:
        """Atomically claim one available job."""
        now = now or datetime.now(timezone.utc)
        statement: Select[tuple[QueueJob]] = (
            select(QueueJob)
            .options(selectinload(QueueJob.document))
            .where(
                or_(
                    QueueJob.status == JobStatus.QUEUED,
                    (
                        (QueueJob.status == JobStatus.RETRY_WAITING)
                        & ((QueueJob.retry_at.is_(None)) | (QueueJob.retry_at <= now))
                    ),
                )
            )
            .order_by(
                case(
                    (QueueJob.status == JobStatus.RETRY_WAITING, 0),
                    else_=1,
                ),
                QueueJob.created_at,
                QueueJob.id,
            )
            .limit(1)
        )
        if self._db.bind and self._db.bind.dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        else:
            statement = statement.with_for_update()

        job = self._db.scalars(statement).first()
        if job is None:
            self._db.rollback()
            return None
        job.status = JobStatus.PROCESSING
        job.worker_id = worker_id
        job.started_at = now
        job.completed_at = None
        job.last_error = None
        job.retry_at = None
        if job.document is not None:
            job.document.processing_status = DocumentProcessingStatus.PROCESSING
        self._db.add(job)
        self._db.commit()
        self._db.refresh(job)
        return job

    def mark_completed(self, job: QueueJob) -> QueueJob:
        """Mark a claimed job successful."""
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        job.worker_id = None
        job.retry_at = None
        self._db.add(job)
        self._db.commit()
        self._db.refresh(job)
        return job

    def mark_failed_attempt(
        self,
        job: QueueJob,
        *,
        error: str,
        retry_backoff_seconds: int,
    ) -> QueueJob:
        """Record a failed attempt and either schedule retry or fail permanently.

        Transient failures move the job to ``RETRY_WAITING`` with an exponential
        backoff deadline: the first retry waits ``1 * backoff`` seconds, the
        second ``2 * backoff``, the third ``4 * backoff``, and so on. When the
        attempt budget (``max_attempts``) is exhausted the job is permanently
        ``FAILED`` and its document is marked failed so operators can see it.

        Args:
            job: The claimed job being processed.
            error: Human-readable failure detail (truncated for storage).
            retry_backoff_seconds: Base delay in seconds for the exponential
                backoff schedule.

        Returns:
            The updated job.
        """
        now = datetime.now(timezone.utc)
        job.attempts += 1
        job.last_error = error[:2000]
        job.worker_id = None
        if job.attempts >= job.max_attempts:
            job.status = JobStatus.FAILED
            job.completed_at = now
            job.retry_at = None
            job.started_at = None
            if job.document is not None:
                job.document.processing_status = DocumentProcessingStatus.FAILED
        else:
            job.status = JobStatus.RETRY_WAITING
            backoff = retry_backoff_seconds * (2 ** (job.attempts - 1))
            job.retry_at = now + timedelta(seconds=backoff)
            job.completed_at = None
            if job.document is not None:
                job.document.processing_status = DocumentProcessingStatus.UPLOADED
        self._db.add(job)
        self._db.commit()
        self._db.refresh(job)
        return job

    def heartbeat(
        self,
        *,
        job_id: int,
        now: datetime | None = None,
    ) -> None:
        """Refresh the liveness lease of a PROCESSING job.

        While a worker processes a job it periodically refreshes ``started_at``
        as a heartbeat. Stale-job recovery only reclaims jobs whose ``started_at``
        is older than the configured timeout, so a live (but slow) worker is
        never falsely declared crashed and its document is never processed twice.

        Args:
            job_id: Id of the job being processed.
            now: Heartbeat timestamp; defaults to the current UTC time.
        """
        now = now or datetime.now(timezone.utc)
        self._db.execute(
            update(QueueJob)
            .where(QueueJob.id == job_id, QueueJob.status == JobStatus.PROCESSING)
            .values(started_at=now)
        )
        self._db.commit()

    def recover_stale_processing(
        self,
        *,
        stale_after_seconds: int,
        now: datetime | None = None,
    ) -> int:
        """Release or fail jobs abandoned in PROCESSING after worker crash.

        A job whose ``started_at`` (refreshed as a heartbeat by the processing
        worker) is older than ``stale_after_seconds`` is considered abandoned.
        If the attempt budget is already exhausted the job is permanently
        ``FAILED``; otherwise it returns to ``QUEUED`` so another worker can pick
        it up. In both cases the worker lease is cleared and the document status
        is reset so no document is ever permanently stuck in ``PROCESSING``.
        Completed jobs are never touched: they are not selected by this query.

        Crashed attempts deliberately do not consume the retry budget: a job
        whose worker crashed repeatedly is requeued again rather than silently
        dropped, so infrastructure failures never burn the document's retries.
        The attempt budget only applies to genuine processing failures.

        Args:
            stale_after_seconds: Age of ``started_at`` after which a PROCESSING
                job is treated as abandoned.
            now: Reference timestamp; defaults to the current UTC time.

        Returns:
            The number of stale jobs recovered.
        """
        now = now or datetime.now(timezone.utc)
        threshold = now - timedelta(seconds=stale_after_seconds)
        jobs = list(
            self._db.scalars(
                select(QueueJob)
                .options(selectinload(QueueJob.document))
                .where(
                    QueueJob.status == JobStatus.PROCESSING,
                    QueueJob.started_at.is_not(None),
                    QueueJob.started_at < threshold,
                )
            ).all()
        )
        for job in jobs:
            job.worker_id = None
            job.last_error = "Recovered stale PROCESSING job (worker crash)"
            job.started_at = None
            job.retry_at = None
            if job.attempts >= job.max_attempts:
                job.status = JobStatus.FAILED
                job.completed_at = now
                if job.document is not None:
                    job.document.processing_status = DocumentProcessingStatus.FAILED
            else:
                job.status = JobStatus.QUEUED
                job.completed_at = None
                if job.document is not None:
                    job.document.processing_status = DocumentProcessingStatus.UPLOADED
        if jobs:
            self._db.commit()
        return len(jobs)

    def progress_for_application(self, application_id: int) -> dict[JobStatus, int]:
        """Return queue counts grouped by status for an application."""
        rows = self._db.execute(
            select(QueueJob.status, func.count())
            .where(QueueJob.application_id == application_id)
            .group_by(QueueJob.status)
        ).all()
        return {status: int(count) for status, count in rows}

    def list_by_application(self, application_id: int) -> Sequence[QueueJob]:
        """Return queue jobs for an application."""
        return self._db.scalars(
            select(QueueJob)
            .where(QueueJob.application_id == application_id)
            .order_by(QueueJob.id)
        ).all()

    def retry_failed_for_application(self, application_id: int) -> int:
        """Requeue failed documents for an explicit operator retry."""
        jobs = list(
            self._db.scalars(
                select(QueueJob)
                .options(selectinload(QueueJob.document))
                .where(
                    QueueJob.application_id == application_id,
                    QueueJob.status == JobStatus.FAILED,
                )
            ).all()
        )
        for job in jobs:
            job.status = JobStatus.QUEUED
            job.attempts = 0
            job.worker_id = None
            job.last_error = None
            job.started_at = None
            job.completed_at = None
            job.retry_at = None
            if job.document is not None:
                job.document.processing_status = DocumentProcessingStatus.UPLOADED
        if jobs:
            self._db.commit()
        return len(jobs)
