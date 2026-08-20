"""Business service for the Performance API.

Computes evidence-backed timing metrics per application from the timestamps the
system itself recorded. The conventions are deliberately conservative: a metric
is only counted when the system has an explicit record of the span (a document
request paired with a receipt, a queue job's active run, the pipeline
completion followed by a review decision). Time between unrelated events is
never counted as belonging to any phase, so a gap while the system sat idle is
not mislabeled as "waiting for the applicant".
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.application import Application
from app.database.models.enums import (
    ApplicationStatus,
    JobStatus,
    JobType,
    ReviewDecision,
    ValidationEventType,
)
from app.database.models.human_review import HumanReview
from app.database.models.queue_job import QueueJob
from app.database.models.validation_history import ValidationHistoryEntry
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.human_review_repository import HumanReviewRepository
from app.database.repositories.queue_job_repository import QueueJobRepository
from app.database.repositories.validation_history_repository import (
    ValidationHistoryRepository,
)
from app.performance.schemas import (
    ApplicationPerformance,
    PerformanceOverview,
    TimeSpan,
)


class ApplicationNotFoundError(Exception):
    """Raised when an application id does not exist."""


def _duration_seconds(start: datetime, end: datetime) -> int:
    """Whole seconds between two timestamps (never negative)."""
    seconds = int((end - start).total_seconds())
    return max(seconds, 0)


def _waiting_spans(
    entries: list[ValidationHistoryEntry], now: datetime
) -> tuple[list[TimeSpan], int]:
    """Pair document requests with their receipts to build waiting spans.

    Each ``DOCUMENTS_REQUESTED`` opens a span that the next
    ``DOCUMENTS_RECEIVED`` closes. An unmatched request (e.g. the bulk-upload
    path, which transitions to PROCESSING before recording a receipt) is kept
    as an *open* span from the request to now: it is shown as evidence but
    never counted in the closed waiting total.

    Args:
        entries: Validation history entries in chronological order.
        now: Reference "now" for open spans.

    Returns:
        The waiting spans and the summed closed waiting seconds.
    """
    spans: list[TimeSpan] = []
    open_start: datetime | None = None
    for entry in entries:
        if entry.event_type is ValidationEventType.DOCUMENTS_REQUESTED:
            if open_start is None:
                open_start = entry.created_at
            else:
                # A second request while one is still open supersedes it: close
                # the earlier span as open (unanswered) and start the new one,
                # preserving the evidence of the first request.
                spans.append(
                    TimeSpan(
                        label="Waiting for documents",
                        start=open_start,
                        end=None,
                        duration_seconds=None,
                        open=True,
                        detail="Request unanswered; superseded by a later request",
                    )
                )
                open_start = entry.created_at
        elif (
            entry.event_type is ValidationEventType.DOCUMENTS_RECEIVED
            and open_start is not None
        ):
            spans.append(
                TimeSpan(
                    label="Waiting for documents",
                    start=open_start,
                    end=entry.created_at,
                    duration_seconds=_duration_seconds(open_start, entry.created_at),
                    open=False,
                )
            )
            open_start = None
    if open_start is not None:
        spans.append(
            TimeSpan(
                label="Waiting for documents",
                start=open_start,
                end=None,
                duration_seconds=None,
                open=True,
                detail="Still waiting for the applicant to upload documents",
            )
        )
    closed_seconds = sum(
        span.duration_seconds for span in spans if span.duration_seconds is not None
    )
    return spans, closed_seconds


def _processing_spans(
    jobs: list[QueueJob], now: datetime
) -> tuple[list[TimeSpan], int]:
    """Build active-processing spans from every queue job.

    A job's active window is ``started_at -> completed_at`` (or ``-> now``
    while the job is still processing or waiting to retry). This is wall-clock
    time the worker actually owned the work, which is the honest measure of
    internal processing.

    Args:
        jobs: All queue jobs for the application (document and pipeline).
        now: Reference "now" for in-flight jobs.

    Returns:
        The processing spans and the summed closed processing seconds.
    """
    spans: list[TimeSpan] = []
    for job in jobs:
        if job.started_at is None:
            continue
        if job.completed_at is not None:
            spans.append(
                TimeSpan(
                    label=f"Processing: {job.job_type.value}",
                    start=job.started_at,
                    end=job.completed_at,
                    duration_seconds=_duration_seconds(job.started_at, job.completed_at),
                    open=False,
                    detail=job.last_error or None,
                )
            )
        else:
            spans.append(
                TimeSpan(
                    label=f"Processing: {job.job_type.value}",
                    start=job.started_at,
                    end=None,
                    duration_seconds=None,
                    open=True,
                    detail=job.last_error or None,
                )
            )
    closed_seconds = sum(
        span.duration_seconds for span in spans if span.duration_seconds is not None
    )
    return spans, closed_seconds


def _review_spans(
    jobs: list[QueueJob],
    reviews: list[HumanReview],
    now: datetime,
    status: ApplicationStatus,
) -> tuple[list[TimeSpan], int]:
    """Build the review span from pipeline completion to the decision.

    The pipeline job's completion transitions the application to
    PENDING_REVIEW, so its ``completed_at`` starts the review window; the
    latest review decision (or "now" while still pending) ends it.

    Args:
        jobs: All queue jobs for the application.
        reviews: Human reviews for the application, newest first.
        now: Reference "now" for an undecided review.
        status: Current application status.

    Returns:
        The review spans and the summed closed review seconds.
    """
    pipeline_completed = None
    for job in jobs:
        if (
            job.job_type is JobType.APPLICATION_PIPELINE
            and job.completed_at is not None
        ):
            pipeline_completed = job.completed_at
    if pipeline_completed is None:
        return [], 0

    latest_review = reviews[0] if reviews else None
    if latest_review is not None and status is not ApplicationStatus.PENDING_REVIEW:
        span = TimeSpan(
            label="Under review",
            start=pipeline_completed,
            end=latest_review.reviewed_at,
            duration_seconds=_duration_seconds(
                pipeline_completed, latest_review.reviewed_at
            ),
            open=False,
            detail=f"Decision: {latest_review.decision.value}",
        )
        return [span], span.duration_seconds

    span = TimeSpan(
        label="Under review",
        start=pipeline_completed,
        end=None,
        duration_seconds=None,
        open=True,
        detail="Review not yet decided",
    )
    return [span], 0


def _decided_at(
    reviews: list[HumanReview], entries: list[ValidationHistoryEntry]
) -> datetime | None:
    """Return when the application reached a final decision, if it has.

    Approval/correction/rejection by a reviewer comes from ``human_reviews``;
    an operator-stage rejection comes from the validation history. If neither
    happened, the application is still in flight and has no decision time.
    """
    if reviews:
        return max(review.reviewed_at for review in reviews)
    rejected_entries = [
        entry
        for entry in entries
        if entry.event_type is ValidationEventType.OPERATOR_REJECTED
    ]
    if rejected_entries:
        return max(entry.created_at for entry in rejected_entries)
    return None


def _build_breakdown(
    application: Application,
    entries: list[ValidationHistoryEntry],
    reviews: list[HumanReview],
    jobs: list[QueueJob],
    now: datetime,
) -> ApplicationPerformance:
    """Assemble one application's performance breakdown with evidence."""
    entries_sorted = sorted(entries, key=lambda e: e.created_at)
    waiting_spans, waiting_seconds = _waiting_spans(entries_sorted, now)
    processing_spans, processing_seconds = _processing_spans(jobs, now)
    review_spans, review_seconds = _review_spans(
        jobs, reviews, now, application.status
    )

    decided_at = _decided_at(reviews, entries)
    turnaround = None
    if decided_at is not None:
        turnaround = _duration_seconds(application.submitted_at, decided_at)
    else:
        turnaround = None  # in flight; not counted as a closed turnaround

    return ApplicationPerformance(
        application_id=application.id,
        application_name=application.name,
        status=application.status,
        submitted_at=application.submitted_at,
        decided_at=decided_at,
        created_by=application.created_by,
        waiting_seconds=waiting_seconds or None,
        processing_seconds=processing_seconds or None,
        review_seconds=review_seconds or None,
        total_turnaround_seconds=turnaround,
        resubmissions=sum(
            1
            for e in entries
            if e.event_type is ValidationEventType.DOCUMENTS_RECEIVED
        ),
        missing_document_cycles=sum(
            1
            for e in entries
            if e.event_type is ValidationEventType.DOCUMENTS_REQUESTED
        ),
        waiting_spans=waiting_spans,
        processing_spans=processing_spans,
        review_spans=review_spans,
    )


class PerformanceService:
    """Compute evidence-backed performance metrics for the IT view."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._applications = ApplicationRepository(db)
        self._history = ValidationHistoryRepository(db)
        self._reviews = HumanReviewRepository(db)
        self._jobs = QueueJobRepository(db)

    def _load_all(self) -> dict[int, dict[str, Any]]:
        """Load every application plus its history/reviews/jobs in bulk.

        Returns a dict keyed by application id with preloaded lists, so the
        overview and per-application pages share one query batch rather than
        N+1-loading per application.
        """
        applications = list(self._applications.list(offset=0, limit=10_000))
        ids = [app.id for app in applications]

        history_by_app: dict[int, list[ValidationHistoryEntry]] = defaultdict(list)
        if ids:
            for entry in self._db.scalars(
                select(ValidationHistoryEntry).where(
                    ValidationHistoryEntry.application_id.in_(ids)
                )
            ).all():
                history_by_app[entry.application_id].append(entry)

        reviews_by_app: dict[int, list[HumanReview]] = defaultdict(list)
        if ids:
            for review in self._db.scalars(
                select(HumanReview).where(HumanReview.application_id.in_(ids))
            ).all():
                reviews_by_app[review.application_id].append(review)
            for reviews in reviews_by_app.values():
                reviews.sort(key=lambda r: r.reviewed_at, reverse=True)

        jobs_by_app: dict[int, list[QueueJob]] = defaultdict(list)
        if ids:
            for job in self._db.scalars(
                select(QueueJob).where(QueueJob.application_id.in_(ids))
            ).all():
                jobs_by_app[job.application_id].append(job)

        return {
            app.id: {
                "application": app,
                "history": history_by_app.get(app.id, []),
                "reviews": reviews_by_app.get(app.id, []),
                "jobs": jobs_by_app.get(app.id, []),
            }
            for app in applications
        }

    def overview(self) -> PerformanceOverview:
        """Compute aggregate performance across all applications."""
        now = datetime.now(timezone.utc)
        data = self._load_all()

        total = len(data)
        decided = 0
        status_counts: dict[str, int] = defaultdict(int)

        waiting_times: list[int] = []
        processing_times: list[int] = []
        review_times: list[int] = []
        turnaround_times: list[int] = []
        total_resubmissions = 0
        total_cycles = 0

        for app_data in data.values():
            breakdown = _build_breakdown(
                application=app_data["application"],
                entries=app_data["history"],
                reviews=app_data["reviews"],
                jobs=app_data["jobs"],
                now=now,
            )
            status_counts[breakdown.status.value] += 1
            if breakdown.decided_at is not None:
                decided += 1
            if breakdown.waiting_seconds is not None:
                waiting_times.append(breakdown.waiting_seconds)
            if breakdown.processing_seconds is not None:
                processing_times.append(breakdown.processing_seconds)
            if breakdown.review_seconds is not None:
                review_times.append(breakdown.review_seconds)
            if breakdown.total_turnaround_seconds is not None:
                turnaround_times.append(breakdown.total_turnaround_seconds)
            total_resubmissions += breakdown.resubmissions
            total_cycles += breakdown.missing_document_cycles

        def _avg(values: list[int]) -> float | None:
            return round(sum(values) / len(values), 1) if values else None

        return PerformanceOverview(
            total_applications=total,
            decided_applications=decided,
            status_counts=dict(status_counts),
            avg_waiting_seconds=_avg(waiting_times),
            avg_processing_seconds=_avg(processing_times),
            avg_review_seconds=_avg(review_times),
            avg_turnaround_seconds=_avg(turnaround_times),
            total_resubmissions=total_resubmissions,
            total_missing_document_cycles=total_cycles,
        )

    def list_applications(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        query: str | None = None,
        status: ApplicationStatus | None = None,
    ) -> tuple[list[ApplicationPerformance], int]:
        """Return paginated per-application performance rows."""
        now = datetime.now(timezone.utc)
        applications, total = self._applications.search(
            offset=offset, limit=limit, query=query, status=status
        )
        if not applications:
            return [], total

        ids = [app.id for app in applications]
        history_by_app: dict[int, list[ValidationHistoryEntry]] = defaultdict(list)
        for entry in self._db.scalars(
            select(ValidationHistoryEntry).where(
                ValidationHistoryEntry.application_id.in_(ids)
            )
        ).all():
            history_by_app[entry.application_id].append(entry)

        reviews_by_app: dict[int, list[HumanReview]] = defaultdict(list)
        for review in self._db.scalars(
            select(HumanReview).where(HumanReview.application_id.in_(ids))
        ).all():
            reviews_by_app[review.application_id].append(review)
        for reviews in reviews_by_app.values():
            reviews.sort(key=lambda r: r.reviewed_at, reverse=True)

        jobs_by_app: dict[int, list[QueueJob]] = defaultdict(list)
        for job in self._db.scalars(
            select(QueueJob).where(QueueJob.application_id.in_(ids))
        ).all():
            jobs_by_app[job.application_id].append(job)

        items = [
            _build_breakdown(
                application=app,
                entries=history_by_app.get(app.id, []),
                reviews=reviews_by_app.get(app.id, []),
                jobs=jobs_by_app.get(app.id, []),
                now=now,
            )
            for app in applications
        ]
        return items, total