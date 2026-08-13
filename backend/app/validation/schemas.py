"""Pydantic models forming the validation module API contract.

The schemas expose a small, focused surface: task creation and listing, task
workflow actions (start, complete, reject, request-correction), task/application
log retrieval, task result retrieval and field/evidence review logging. No
user/operator fields are exposed -- those arrive with the separate User/Operator
module.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.database.models.enums import (
    Severity,
    ValidationLogAction,
    ValidationLogCheckType,
    ValidationLogResult,
    ValidationStatus,
    ValidationTaskPriority,
    ValidationTaskStatus,
)


class ValidationTaskCreate(BaseModel):
    """Payload creating a new validation task for an application.

    Attributes:
        application_id: Id of the application being validated.
        priority: Scheduling priority of the task.
    """

    application_id: int = Field(gt=0)
    priority: ValidationTaskPriority = ValidationTaskPriority.NORMAL


class ValidationTaskRead(BaseModel):
    """Serialized validation task as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    status: ValidationTaskStatus
    priority: ValidationTaskPriority
    validation_run_id: int | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ValidationTaskList(BaseModel):
    """Paginated validation task listing.

    Attributes:
        tasks: Tasks on the current page.
        total: Total number of tasks matching the filters.
        offset: Number of rows skipped.
        limit: Maximum number of rows returned.
    """

    tasks: list[ValidationTaskRead] = Field(default_factory=list)
    total: int
    offset: int
    limit: int


class ValidationLogRead(BaseModel):
    """Serialized immutable validation log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    validation_task_id: int
    application_id: int
    validation_run_id: int | None
    action: ValidationLogAction
    check_type: ValidationLogCheckType | None
    field_name: str | None
    previous_value: str | None
    new_value: str | None
    result: ValidationLogResult | None
    reason: str | None
    created_at: datetime


class ValidationLogList(BaseModel):
    """Paginated validation log listing.

    Attributes:
        logs: Log entries on the current page.
        total: Total number of log entries.
        offset: Number of rows skipped.
        limit: Maximum number of rows returned.
    """

    logs: list[ValidationLogRead] = Field(default_factory=list)
    total: int
    offset: int
    limit: int


class CompleteRequest(BaseModel):
    """Payload completing a validation task.

    Attributes:
        comment: Optional free-form note attached to the completion.
    """

    comment: str | None = None


class RejectRequest(BaseModel):
    """Payload rejecting a validation task.

    Attributes:
        reason: Mandatory explanation for the rejection.
    """

    reason: str = Field(min_length=1, max_length=2000)


class RequestCorrectionRequest(BaseModel):
    """Payload requesting a correction on a validation task.

    Attributes:
        reason: Mandatory explanation of the issue to correct.
    """

    reason: str = Field(min_length=1, max_length=2000)


class FieldVerifyRequest(BaseModel):
    """Payload recording a field verification event.

    Attributes:
        validation_task_id: Task the event belongs to.
        result: Outcome of the manual verification (e.g. ``CONFIRMED``).
        comment: Optional free-form note.
    """

    validation_task_id: int = Field(gt=0)
    result: ValidationLogResult
    comment: str | None = None


class FieldCorrectRequest(BaseModel):
    """Payload recording a field correction event.

    Attributes:
        validation_task_id: Task the event belongs to.
        corrected_value: Value confirmed by the reviewer.
        reason: Optional explanation for the correction.
    """

    validation_task_id: int = Field(gt=0)
    corrected_value: str = Field(min_length=1, max_length=4000)
    reason: str | None = None


class EvidenceReviewRequest(BaseModel):
    """Payload recording a signature/stamp evidence review.

    Attributes:
        validation_task_id: Task the event belongs to.
        result: Outcome of the review (e.g. ``CONFIRMED``, ``REQUIRES_REVIEW``).
        comment: Optional free-form note.
    """

    validation_task_id: int = Field(gt=0)
    result: ValidationLogResult
    comment: str | None = None


class ValidationResultItem(BaseModel):
    """One stored validation check result shown for a task.

    Only the columns needed for review are exposed; the heavy payload of the
    full validation report stays with the reports module.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    document_id: int | None
    rule_id: str
    rule_name: str
    rule_category: str
    severity: Severity
    status: ValidationStatus
    message: str | None
    validated_at: datetime


class ValidationResultList(BaseModel):
    """Paginated validation check results for a task's application."""

    results: list[ValidationResultItem] = Field(default_factory=list)
    total: int
    offset: int
    limit: int


class ErrorResponse(BaseModel):
    """Standard error response body.

    Attributes:
        detail: Human-readable error description.
    """

    detail: str


__all__ = [
    "CompleteRequest",
    "ErrorResponse",
    "EvidenceReviewRequest",
    "FieldCorrectRequest",
    "FieldVerifyRequest",
    "RejectRequest",
    "RequestCorrectionRequest",
    "ValidationLogList",
    "ValidationLogRead",
    "ValidationResultItem",
    "ValidationResultList",
    "ValidationTaskCreate",
    "ValidationTaskList",
    "ValidationTaskRead",
]