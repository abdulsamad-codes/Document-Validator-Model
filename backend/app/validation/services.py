"""Validation module services.

``ValidationTaskService`` owns the validation workflow: it creates tasks (with
their versioned validation run and initial log), retrieves/queues them and
drives the state machine (start, complete, reject, request-correction).
``ValidationLogService`` records and retrieves the immutable validation log and
logs review-time field and evidence events.

Every state-changing operation is a single transaction: the repositories flush
(never commit) and the service commits exactly once, rolling back on any
failure so a task transition can never persist without its accompanying log
entry. State transitions lock the task row (``SELECT ... FOR UPDATE``) so
concurrent requests cannot race.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database.models.enums import (
    ValidationLogAction,
    ValidationLogCheckType,
    ValidationLogResult,
    ValidationTaskPriority,
    ValidationTaskStatus,
)
from app.validation.constants import MODULE_VERSION
from app.validation.exceptions import (
    InvalidValidationState,
    ValidationApplicationNotFound,
    ValidationError,
    ValidationEvidenceNotFound,
    ValidationFieldNotFound,
    ValidationLogCreationError,
    ValidationTaskCreationError,
    ValidationTaskNotFound,
)
from app.validation.repositories import (
    ApplicationRepository,
    ExtractedFieldRepository,
    ValidationLogRepository,
    ValidationRepository,
    ValidationRunRepository,
    ValidationTaskRepository,
    VisualDetectionRepository,
)
from app.validation.schemas import ValidationResultItem
from app.validation.validators import (
    ensure_transition,
    require_reason,
    require_task_in_review,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Return the current UTC time with timezone information."""
    return datetime.now(timezone.utc)


def check_type_for_field(field_name: str) -> ValidationLogCheckType:
    """Map a field name to its check type for logging.

    Args:
        field_name: Machine-readable name of the extracted field.

    Returns:
        The matching check type, or ``GENERAL`` for unrecognized fields.
    """
    lowered = field_name.lower()
    if "account_number" in lowered or "account no" in lowered:
        return ValidationLogCheckType.ACCOUNT_NUMBER
    if "ntn" in lowered:
        return ValidationLogCheckType.NTN
    if "bank_name" in lowered or "bank name" in lowered:
        return ValidationLogCheckType.BANK_NAME
    if "account_title" in lowered or "account title" in lowered:
        return ValidationLogCheckType.ACCOUNT_TITLE
    return ValidationLogCheckType.GENERAL


def evidence_action_for(detection_type: str) -> tuple[ValidationLogAction, ValidationLogCheckType]:
    """Map a detection type to its log action and check type.

    Args:
        detection_type: Opaque detection kind (e.g. ``SIGNATURE``, ``STAMP``).

    Returns:
        A ``(action, check_type)`` pair; unknown kinds become a document
        review.
    """
    normalized = detection_type.strip().upper()
    if normalized == "SIGNATURE":
        return ValidationLogAction.SIGNATURE_REVIEWED, ValidationLogCheckType.SIGNATURE
    if normalized == "STAMP":
        return ValidationLogAction.STAMP_REVIEWED, ValidationLogCheckType.STAMP
    return ValidationLogAction.DOCUMENT_REVIEWED, ValidationLogCheckType.DOCUMENT_REVIEW


class ValidationTaskService:
    """Create, retrieve and drive validation tasks through their workflow.

    Args:
        db: Active database session.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._applications = ApplicationRepository(db)
        self._runs = ValidationRunRepository(db)
        self._tasks = ValidationTaskRepository(db)
        self._logs = ValidationLogRepository(db)
        self._results = ValidationRepository(db)

    # -- Public API -----------------------------------------------------------

    def create_task(
        self,
        *,
        application_id: int,
        priority: ValidationTaskPriority = ValidationTaskPriority.NORMAL,
    ):
        """Create a new validation task for an application.

        A new versioned validation run is created (run number incremented per
        application), the task references it and a ``TASK_CREATED`` log entry
        records the event -- all in one transaction. Only one active task is
        allowed per application at a time; a completed or returned-for-
        correction application can receive a new task (revalidation).

        Args:
            application_id: Application being validated.
            priority: Scheduling priority of the task.

        Returns:
            The persisted validation task.

        Raises:
            ValidationApplicationNotFound: When the application does not exist.
            InvalidValidationState: When the application already has an active
                validation task.
            ValidationTaskCreationError: When the task could not be persisted.
        """
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ValidationApplicationNotFound()
        if self._tasks.get_active_for_application(application_id) is not None:
            raise InvalidValidationState(
                "The application already has an active validation task"
            )
        try:
            run_number = self._runs.next_run_number(application_id)
            run = self._runs.create(
                application_id=application_id,
                run_number=run_number,
            )
            task = self._tasks.create(
                application_id=application_id,
                validation_run_id=run.id,
                priority=priority,
            )
            self._logs.create(
                validation_task_id=task.id,
                application_id=application_id,
                validation_run_id=run.id,
                action=ValidationLogAction.TASK_CREATED,
                result=ValidationLogResult.INFO,
                reason=f"validation module version {MODULE_VERSION}",
            )
            self._db.commit()
        except ValidationError:
            self._db.rollback()
            raise
        except Exception as exc:
            self._db.rollback()
            logger.exception("Validation task creation failed")
            raise ValidationTaskCreationError() from exc

        logger.info(
            "Validation task created id=%s application_id=%s run_number=%s",
            task.id,
            application_id,
            run_number,
        )
        return task

    def get_task(self, *, task_id: int):
        """Return a validation task or raise ``ValidationTaskNotFound``.

        Args:
            task_id: Id of the task.

        Returns:
            The validation task.

        Raises:
            ValidationTaskNotFound: When the task does not exist.
        """
        task = self._tasks.get_by_id(task_id)
        if task is None:
            raise ValidationTaskNotFound()
        return task

    def list_tasks(
        self,
        *,
        status: ValidationTaskStatus | None = None,
        priority: ValidationTaskPriority | None = None,
        offset: int = 0,
        limit: int = 50,
    ):
        """List validation tasks for the operator queue.

        Args:
            status: When given, only return tasks in this status.
            priority: When given, only return tasks of this priority.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A ``(tasks, total)`` pair; ``tasks`` is the current page.
        """
        tasks = self._tasks.list(
            status=status,
            priority=priority,
            offset=offset,
            limit=limit,
        )
        total = self._tasks.count(status=status, priority=priority)
        return tasks, total

    def start_validation(self, *, task_id: int):
        """Start validation for a task, atomically.

        Locks the task row, verifies it is PENDING, moves it to IN_REVIEW with
        ``started_at`` set and records a ``TASK_STARTED`` log entry -- all in a
        single transaction. The row lock makes concurrent starts impossible.

        Args:
            task_id: Id of the task.

        Returns:
            The started task.

        Raises:
            ValidationTaskNotFound: When the task does not exist.
            ValidationError: When the task cannot be started from its current
                state.
        """
        try:
            task = self._tasks.get_by_id_locked(task_id)
            if task is None:
                raise ValidationTaskNotFound()
            ensure_transition(task.status, ValidationTaskStatus.IN_REVIEW)
            self._tasks.update(
                task,
                status=ValidationTaskStatus.IN_REVIEW,
                started_at=_utcnow(),
            )
            self._logs.create(
                validation_task_id=task.id,
                application_id=task.application_id,
                validation_run_id=task.validation_run_id,
                action=ValidationLogAction.TASK_STARTED,
                result=ValidationLogResult.INFO,
            )
            self._db.commit()
        except ValidationError:
            self._db.rollback()
            raise
        except Exception as exc:
            self._db.rollback()
            logger.exception("Validation task start failed")
            raise ValidationLogCreationError() from exc

        logger.info("Validation task started id=%s", task.id)
        return task

    def complete_validation(self, *, task_id: int, comment: str | None = None):
        """Complete validation for a task, atomically.

        Locks the task row, verifies it can be validated, moves it to VALIDATED
        with ``completed_at`` set and records a ``VALIDATION_COMPLETED`` log
        entry -- all in a single transaction.

        Args:
            task_id: Id of the task.
            comment: Optional free-form note stored on the log entry.

        Returns:
            The completed task.

        Raises:
            ValidationTaskNotFound: When the task does not exist.
            ValidationError: When the task cannot be completed from its current
                state.
        """
        try:
            task = self._tasks.get_by_id_locked(task_id)
            if task is None:
                raise ValidationTaskNotFound()
            ensure_transition(task.status, ValidationTaskStatus.VALIDATED)
            self._tasks.update(
                task,
                status=ValidationTaskStatus.VALIDATED,
                completed_at=_utcnow(),
            )
            self._logs.create(
                validation_task_id=task.id,
                application_id=task.application_id,
                validation_run_id=task.validation_run_id,
                action=ValidationLogAction.VALIDATION_COMPLETED,
                result=ValidationLogResult.PASS,
                reason=comment,
            )
            self._db.commit()
        except ValidationError:
            self._db.rollback()
            raise
        except Exception as exc:
            self._db.rollback()
            logger.exception("Validation task completion failed")
            raise ValidationLogCreationError() from exc

        logger.info("Validation task completed id=%s", task.id)
        return task

    def reject_validation(self, *, task_id: int, reason: str):
        """Reject validation for a task, atomically.

        Locks the task row, verifies it can be rejected, moves it to REJECTED
        with ``completed_at`` set and records a ``VALIDATION_REJECTED`` log
        entry carrying the mandatory reason -- all in a single transaction.

        Args:
            task_id: Id of the task.
            reason: Mandatory explanation for the rejection.

        Returns:
            The rejected task.

        Raises:
            ValidationTaskNotFound: When the task does not exist.
            MissingReason: When no reason is provided.
            ValidationError: When the task cannot be rejected from its current
                state.
        """
        required_reason = require_reason(reason)
        try:
            task = self._tasks.get_by_id_locked(task_id)
            if task is None:
                raise ValidationTaskNotFound()
            ensure_transition(task.status, ValidationTaskStatus.REJECTED)
            self._tasks.update(
                task,
                status=ValidationTaskStatus.REJECTED,
                completed_at=_utcnow(),
            )
            self._logs.create(
                validation_task_id=task.id,
                application_id=task.application_id,
                validation_run_id=task.validation_run_id,
                action=ValidationLogAction.VALIDATION_REJECTED,
                result=ValidationLogResult.REJECTED,
                reason=required_reason,
            )
            self._db.commit()
        except ValidationError:
            self._db.rollback()
            raise
        except Exception as exc:
            self._db.rollback()
            logger.exception("Validation task rejection failed")
            raise ValidationLogCreationError() from exc

        logger.info("Validation task rejected id=%s", task.id)
        return task

    def request_correction(self, *, task_id: int, reason: str):
        """Request a correction on a task, atomically.

        Locks the task row, verifies the task is in review, moves it to
        NEEDS_CORRECTION with ``completed_at`` set and records a
        ``CORRECTION_REQUESTED`` log entry carrying the mandatory reason -- all
        in a single transaction. Corrected documents then produce a brand new
        task/run, preserving this run's history.

        Args:
            task_id: Id of the task.
            reason: Mandatory explanation of the issue to correct.

        Returns:
            The task moved to NEEDS_CORRECTION.

        Raises:
            ValidationTaskNotFound: When the task does not exist.
            MissingReason: When no reason is provided.
            ValidationError: When the task cannot be corrected from its current
                state.
        """
        required_reason = require_reason(reason)
        try:
            task = self._tasks.get_by_id_locked(task_id)
            if task is None:
                raise ValidationTaskNotFound()
            ensure_transition(task.status, ValidationTaskStatus.NEEDS_CORRECTION)
            self._tasks.update(
                task,
                status=ValidationTaskStatus.NEEDS_CORRECTION,
                completed_at=_utcnow(),
            )
            self._logs.create(
                validation_task_id=task.id,
                application_id=task.application_id,
                validation_run_id=task.validation_run_id,
                action=ValidationLogAction.CORRECTION_REQUESTED,
                result=ValidationLogResult.REQUIRES_REVIEW,
                reason=required_reason,
            )
            self._db.commit()
        except ValidationError:
            self._db.rollback()
            raise
        except Exception as exc:
            self._db.rollback()
            logger.exception("Validation task correction request failed")
            raise ValidationLogCreationError() from exc

        logger.info("Correction requested for validation task id=%s", task.id)
        return task

    def get_results(
        self,
        *,
        task_id: int,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ValidationResultItem], int]:
        """Return the stored validation check results for a task's application.

        Results are consumed from the existing ``validation_results`` table
        written by the rule engine and technical validation; nothing is
        re-run here.

        Args:
            task_id: Id of the task.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A ``(results, total)`` pair; ``results`` is the current page.

        Raises:
            ValidationTaskNotFound: When the task does not exist.
        """
        task = self.get_task(task_id=task_id)
        rows = self._results.get_by_application(
            task.application_id,
            offset=offset,
            limit=limit,
        )
        results = [ValidationResultItem.model_validate(row) for row in rows]
        total = self._results.count_by_application(task.application_id)
        return results, total


class ValidationLogService:
    """Record and retrieve the immutable validation log.

    Args:
        db: Active database session.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._tasks = ValidationTaskRepository(db)
        self._logs = ValidationLogRepository(db)
        self._fields = ExtractedFieldRepository(db)
        self._detections = VisualDetectionRepository(db)
        self._applications = ApplicationRepository(db)

    # -- Public API -----------------------------------------------------------

    def get_logs_for_task(
        self,
        *,
        task_id: int,
        offset: int = 0,
        limit: int = 50,
    ):
        """Return the log entries for a task, most recent first.

        Args:
            task_id: Id of the task.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A ``(logs, total)`` pair.

        Raises:
            ValidationTaskNotFound: When the task does not exist.
        """
        self.get_task(task_id)
        logs = self._logs.get_by_task(task_id, offset=offset, limit=limit)
        total = self._logs.count_by_task(task_id)
        return list(logs), total

    def get_logs_for_application(
        self,
        *,
        application_id: int,
        offset: int = 0,
        limit: int = 50,
    ):
        """Return the log entries for an application, most recent first.

        Args:
            application_id: Id of the application.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A ``(logs, total)`` pair.

        Raises:
            ValidationApplicationNotFound: When the application does not exist.
        """
        if self._applications.get_by_id(application_id) is None:
            raise ValidationApplicationNotFound()
        logs = self._logs.get_by_application(
            application_id,
            offset=offset,
            limit=limit,
        )
        total = self._logs.count_by_application(application_id)
        return list(logs), total

    def record_field_verification(
        self,
        *,
        task_id: int,
        field_id: int,
        result: ValidationLogResult,
        comment: str | None = None,
    ):
        """Record a manual field verification event.

        The task must be in review. The extracted field is read (never
        modified -- the human verification module owns field corrections) and a
        ``FIELD_VERIFIED`` log entry is created, preserving the field's current
        value.

        Args:
            task_id: Id of the task.
            field_id: Id of the extracted field being verified.
            result: Outcome of the verification.
            comment: Optional free-form note.

        Returns:
            The created log entry.

        Raises:
            ValidationTaskNotFound: When the task does not exist.
            ValidationTaskNotReady: When the task is not IN_REVIEW.
            ValidationFieldNotFound: When the field does not exist.
            ValidationLogCreationError: When the event could not be persisted.
        """
        task = self._require_reviewable_task(task_id)
        field = self._fields.get_by_id(field_id)
        if field is None:
            raise ValidationFieldNotFound()
        current = field.human_corrected_value or field.extracted_value
        return self._persist_log(
            task,
            action=ValidationLogAction.FIELD_VERIFIED,
            check_type=check_type_for_field(field.field_name),
            field_name=field.field_name,
            previous_value=current,
            new_value=current,
            result=result,
            reason=comment,
        )

    def record_field_correction(
        self,
        *,
        task_id: int,
        field_id: int,
        corrected_value: str,
        reason: str | None = None,
    ):
        """Record a manual field correction event.

        The task must be in review. The extracted field is read (never
        modified -- the human verification module owns field corrections) and a
        ``FIELD_CORRECTED`` log entry is created with the original value
        preserved in ``previous_value`` and the reviewer's value in
        ``new_value``.

        Args:
            task_id: Id of the task.
            field_id: Id of the extracted field being corrected.
            corrected_value: Value confirmed by the reviewer.
            reason: Optional explanation for the correction.

        Returns:
            The created log entry.

        Raises:
            ValidationTaskNotFound: When the task does not exist.
            ValidationTaskNotReady: When the task is not IN_REVIEW.
            ValidationFieldNotFound: When the field does not exist.
            ValidationLogCreationError: When the event could not be persisted.
        """
        task = self._require_reviewable_task(task_id)
        field = self._fields.get_by_id(field_id)
        if field is None:
            raise ValidationFieldNotFound()
        original = field.human_corrected_value or field.extracted_value
        return self._persist_log(
            task,
            action=ValidationLogAction.FIELD_CORRECTED,
            check_type=check_type_for_field(field.field_name),
            field_name=field.field_name,
            previous_value=original,
            new_value=corrected_value,
            result=ValidationLogResult.CORRECTED,
            reason=reason,
        )

    def record_evidence_review(
        self,
        *,
        task_id: int,
        evidence_id: int,
        result: ValidationLogResult,
        comment: str | None = None,
    ):
        """Record a signature/stamp evidence review event.

        The task must be in review. The visual detection row is read and a
        ``SIGNATURE_REVIEWED``/``STAMP_REVIEWED`` (or ``DOCUMENT_REVIEWED``) log
        entry is created with the stored detection outcome preserved. Presence
        detection is reported as-is; it does not claim authenticity.

        Args:
            task_id: Id of the task.
            evidence_id: Id of the visual detection row being reviewed.
            result: Outcome of the review.
            comment: Optional free-form note.

        Returns:
            The created log entry.

        Raises:
            ValidationTaskNotFound: When the task does not exist.
            ValidationTaskNotReady: When the task is not IN_REVIEW.
            ValidationEvidenceNotFound: When the detection row does not exist.
            ValidationLogCreationError: When the event could not be persisted.
        """
        task = self._require_reviewable_task(task_id)
        detection = self._detections.get_by_id(evidence_id)
        if detection is None:
            raise ValidationEvidenceNotFound()
        action, check_type = evidence_action_for(detection.detection_type)
        outcome = "PRESENT" if detection.is_present else "NOT_PRESENT"
        return self._persist_log(
            task,
            action=action,
            check_type=check_type,
            field_name=detection.detection_type,
            previous_value=outcome,
            new_value=outcome,
            result=result,
            reason=comment,
        )

    # -- Internals ------------------------------------------------------------

    def get_task(self, task_id: int):
        """Return the task or raise ``ValidationTaskNotFound``."""
        task = self._tasks.get_by_id(task_id)
        if task is None:
            raise ValidationTaskNotFound()
        return task

    def _require_reviewable_task(self, task_id: int):
        """Return the task after asserting it exists and is IN_REVIEW."""
        task = self.get_task(task_id)
        require_task_in_review(task.status)
        return task

    def _persist_log(self, task, **kwargs):
        """Create a log entry and commit once, rolling back on failure."""
        try:
            log = self._logs.create(
                validation_task_id=task.id,
                application_id=task.application_id,
                validation_run_id=task.validation_run_id,
                **kwargs,
            )
            self._db.commit()
        except ValidationError:
            self._db.rollback()
            raise
        except Exception as exc:
            self._db.rollback()
            logger.exception("Validation log entry could not be persisted")
            raise ValidationLogCreationError() from exc
        logger.info(
            "Validation log entry created task_id=%s action=%s",
            task.id,
            log.action.value,
        )
        return log


__all__ = [
    "ValidationLogService",
    "ValidationTaskService",
    "check_type_for_field",
    "evidence_action_for",
]
