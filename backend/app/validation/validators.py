"""Pure validation helpers for the validation module.

Everything here is a deterministic function of the task state or the request
payload, so the transition and payload rules can be unit-tested without a
database. The service consults these helpers before touching the database; no
persistence or pipeline logic ever lives here.
"""

from __future__ import annotations

from app.database.models.enums import ValidationTaskStatus
from app.validation.constants import TRANSITIONS
from app.validation.exceptions import (
    InvalidValidationState,
    MissingReason,
    ValidationAlreadyCompleted,
    ValidationAlreadyRejected,
    ValidationAlreadyStarted,
    ValidationTaskNotReady,
)


def ensure_transition(
    current: ValidationTaskStatus,
    target: ValidationTaskStatus,
) -> None:
    """Verify that ``current -> target`` is a legal task transition.

    Args:
        current: Current task status.
        target: Requested task status.

    Raises:
        ValidationAlreadyStarted: When trying to start a task that is not
            PENDING.
        ValidationAlreadyCompleted: When trying to complete an already
            completed task.
        ValidationAlreadyRejected: When trying to reject an already rejected
            task.
        ValidationTaskNotReady: When a review-time action is attempted on a
            task that is still PENDING.
        InvalidValidationState: For any other illegal transition.
    """
    allowed = TRANSITIONS.get(current, ())
    if target in allowed:
        return
    if current is ValidationTaskStatus.PENDING:
        raise ValidationTaskNotReady()
    if current is ValidationTaskStatus.VALIDATED:
        raise ValidationAlreadyCompleted()
    if current is ValidationTaskStatus.REJECTED:
        raise ValidationAlreadyRejected()
    if current is ValidationTaskStatus.IN_REVIEW:
        raise ValidationAlreadyStarted()
    raise InvalidValidationState(
        f"Cannot move a validation task from {current.value} to {target.value}"
    )


def require_reason(reason: str | None) -> str:
    """Return the trimmed reason or raise ``MissingReason``.

    Args:
        reason: Reason supplied by the caller.

    Returns:
        The trimmed, non-empty reason.

    Raises:
        MissingReason: When the reason is ``None`` or whitespace only.
    """
    if not reason or not reason.strip():
        raise MissingReason()
    return reason.strip()


def require_task_in_review(status: ValidationTaskStatus) -> None:
    """Require a task to be in review before a review-time action runs.

    Args:
        status: Current task status.

    Raises:
        ValidationTaskNotReady: When the task is not IN_REVIEW.
    """
    if status is not ValidationTaskStatus.IN_REVIEW:
        raise ValidationTaskNotReady()


__all__ = [
    "ensure_transition",
    "require_reason",
    "require_task_in_review",
]
