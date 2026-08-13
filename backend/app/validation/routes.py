"""HTTP endpoints for the validation module.

Exposes the validation task workflow (create, list, retrieve, start, complete,
reject, request-correction), the immutable validation logs (per task and per
application), the stored check results for review, and review-time field and
signature/stamp evidence logging. Routes stay thin: they build the service per
request and translate the module's domain exceptions into documented HTTP
errors. No authentication/authorization is applied here -- the separate
User/Operator module attaches it later.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.models.enums import (
    ValidationLogResult,
    ValidationTaskPriority,
    ValidationTaskStatus,
)
from app.validation.constants import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from app.validation.exceptions import ValidationError
from app.validation.schemas import (
    CompleteRequest,
    ErrorResponse,
    EvidenceReviewRequest,
    FieldCorrectRequest,
    FieldVerifyRequest,
    RejectRequest,
    RequestCorrectionRequest,
    ValidationLogList,
    ValidationLogRead,
    ValidationResultList,
    ValidationTaskCreate,
    ValidationTaskList,
    ValidationTaskRead,
)
from app.validation.services import ValidationLogService, ValidationTaskService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["validation"])

_GET_DB = Annotated[Session, Depends(get_db)]

#: Shared OpenAPI error-response documentation reused by every endpoint.
_ERROR_RESPONSES = {
    400: {
        "model": ErrorResponse,
        "description": "Action requires the task to be in review.",
    },
    404: {
        "model": ErrorResponse,
        "description": "Task, application, field or evidence not found.",
    },
    409: {
        "model": ErrorResponse,
        "description": "Illegal state transition or active task conflict.",
    },
    422: {
        "model": ErrorResponse,
        "description": "Invalid request data or missing mandatory reason.",
    },
    500: {
        "model": ErrorResponse,
        "description": "State could not be persisted with its log entry.",
    },
}


def _handle_validation_errors(func):
    """Translate validation module errors into HTTP error responses."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValidationError as exc:
            logger.error(
                "Validation error %s: %s",
                exc.__class__.__name__,
                exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return wrapper


def _task_service(db: Session) -> ValidationTaskService:
    """Build the task service bound to the request session."""
    return ValidationTaskService(db)


def _log_service(db: Session) -> ValidationLogService:
    """Build the log service bound to the request session."""
    return ValidationLogService(db)


# -- Validation task lifecycle -----------------------------------------------


@router.post(
    "/validation/tasks",
    response_model=ValidationTaskRead,
    status_code=201,
    summary="Create a validation task",
    description=(
        "Creates a new versioned validation run and task for an application "
        "and records a TASK_CREATED log entry. Only one active task is allowed "
        "per application; a corrected application can receive a new task "
        "(revalidation) which preserves the historical runs."
    ),
    responses={
        404: _ERROR_RESPONSES[404],
        409: _ERROR_RESPONSES[409],
        422: _ERROR_RESPONSES[422],
        500: _ERROR_RESPONSES[500],
    },
)
@_handle_validation_errors
def create_validation_task(
    request: ValidationTaskCreate,
    db: _GET_DB,
) -> ValidationTaskRead:
    """Create a new validation task for an application."""
    return _task_service(db).create_task(
        application_id=request.application_id,
        priority=request.priority,
    )


@router.get(
    "/validation/tasks",
    response_model=ValidationTaskList,
    summary="List validation tasks",
    description=(
        "Returns the validation queue, optionally filtered by status and "
        "priority and paginated. Tasks are ordered for the queue (status, then "
        "priority, then creation time)."
    ),
    responses={404: _ERROR_RESPONSES[404]},
)
@_handle_validation_errors
def list_validation_tasks(
    db: _GET_DB,
    status: ValidationTaskStatus | None = None,
    priority: ValidationTaskPriority | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
) -> ValidationTaskList:
    """List validation tasks for the queue."""
    tasks, total = _task_service(db).list_tasks(
        status=status,
        priority=priority,
        offset=offset,
        limit=limit,
    )
    return ValidationTaskList(
        tasks=tasks,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/validation/tasks/{task_id}",
    response_model=ValidationTaskRead,
    summary="Get a validation task",
    description="Returns a single validation task by id.",
    responses={404: _ERROR_RESPONSES[404]},
)
@_handle_validation_errors
def get_validation_task(
    task_id: int,
    db: _GET_DB,
) -> ValidationTaskRead:
    """Return a validation task."""
    return _task_service(db).get_task(task_id=task_id)


@router.post(
    "/validation/tasks/{task_id}/start",
    response_model=ValidationTaskRead,
    summary="Start validation",
    description=(
        "Atomically moves a PENDING task to IN_REVIEW, sets started_at and "
        "records a TASK_STARTED log entry. The task row is locked so concurrent "
        "starts cannot race."
    ),
    responses={
        400: _ERROR_RESPONSES[400],
        404: _ERROR_RESPONSES[404],
        409: _ERROR_RESPONSES[409],
        500: _ERROR_RESPONSES[500],
    },
)
@_handle_validation_errors
def start_validation(
    task_id: int,
    db: _GET_DB,
) -> ValidationTaskRead:
    """Start validation for a task."""
    return _task_service(db).start_validation(task_id=task_id)


@router.post(
    "/validation/tasks/{task_id}/complete",
    response_model=ValidationTaskRead,
    summary="Complete validation",
    description=(
        "Atomically moves an IN_REVIEW task to VALIDATED, sets completed_at and "
        "records a VALIDATION_COMPLETED log entry."
    ),
    responses={
        400: _ERROR_RESPONSES[400],
        404: _ERROR_RESPONSES[404],
        409: _ERROR_RESPONSES[409],
        500: _ERROR_RESPONSES[500],
    },
)
@_handle_validation_errors
def complete_validation(
    task_id: int,
    request: CompleteRequest,
    db: _GET_DB,
) -> ValidationTaskRead:
    """Complete validation for a task."""
    return _task_service(db).complete_validation(
        task_id=task_id,
        comment=request.comment,
    )


@router.post(
    "/validation/tasks/{task_id}/reject",
    response_model=ValidationTaskRead,
    summary="Reject validation",
    description=(
        "Atomically moves an IN_REVIEW task to REJECTED, sets completed_at and "
        "records a VALIDATION_REJECTED log entry with the mandatory reason."
    ),
    responses={
        400: _ERROR_RESPONSES[400],
        404: _ERROR_RESPONSES[404],
        409: _ERROR_RESPONSES[409],
        422: _ERROR_RESPONSES[422],
        500: _ERROR_RESPONSES[500],
    },
)
@_handle_validation_errors
def reject_validation(
    task_id: int,
    request: RejectRequest,
    db: _GET_DB,
) -> ValidationTaskRead:
    """Reject validation for a task."""
    return _task_service(db).reject_validation(
        task_id=task_id,
        reason=request.reason,
    )


@router.post(
    "/validation/tasks/{task_id}/request-correction",
    response_model=ValidationTaskRead,
    summary="Request a correction",
    description=(
        "Atomically moves an IN_REVIEW task to NEEDS_CORRECTION, sets "
        "completed_at and records a CORRECTION_REQUESTED log entry with the "
        "mandatory reason. Corrected documents then create a brand new task/run, "
        "preserving this run's history."
    ),
    responses={
        400: _ERROR_RESPONSES[400],
        404: _ERROR_RESPONSES[404],
        409: _ERROR_RESPONSES[409],
        422: _ERROR_RESPONSES[422],
        500: _ERROR_RESPONSES[500],
    },
)
@_handle_validation_errors
def request_correction(
    task_id: int,
    request: RequestCorrectionRequest,
    db: _GET_DB,
) -> ValidationTaskRead:
    """Request a correction on a task."""
    return _task_service(db).request_correction(
        task_id=task_id,
        reason=request.reason,
    )


# -- Validation results and logs ---------------------------------------------


@router.get(
    "/validation/tasks/{task_id}/results",
    response_model=ValidationResultList,
    summary="Get validation check results",
    description=(
        "Returns the stored validation check results (rule engine and technical "
        "validation) for the task's application. Nothing is re-run."
    ),
    responses={404: _ERROR_RESPONSES[404]},
)
@_handle_validation_errors
def get_task_results(
    task_id: int,
    db: _GET_DB,
    offset: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
) -> ValidationResultList:
    """Return the stored check results for a task's application."""
    results, total = _task_service(db).get_results(
        task_id=task_id,
        offset=offset,
        limit=limit,
    )
    return ValidationResultList(
        results=results,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/validation/tasks/{task_id}/logs",
    response_model=ValidationLogList,
    summary="Get validation logs for a task",
    description=(
        "Returns the immutable validation log entries for a task, most recent "
        "first and paginated."
    ),
    responses={404: _ERROR_RESPONSES[404]},
)
@_handle_validation_errors
def get_task_logs(
    task_id: int,
    db: _GET_DB,
    offset: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
) -> ValidationLogList:
    """Return the log entries for a task."""
    logs, total = _log_service(db).get_logs_for_task(
        task_id=task_id,
        offset=offset,
        limit=limit,
    )
    return ValidationLogList(
        logs=logs,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/validation/applications/{application_id}/logs",
    response_model=ValidationLogList,
    summary="Get validation logs for an application",
    description=(
        "Returns the immutable validation log entries for an application across "
        "all of its runs, most recent first and paginated."
    ),
    responses={404: _ERROR_RESPONSES[404]},
)
@_handle_validation_errors
def get_application_logs(
    application_id: int,
    db: _GET_DB,
    offset: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
) -> ValidationLogList:
    """Return the log entries for an application."""
    logs, total = _log_service(db).get_logs_for_application(
        application_id=application_id,
        offset=offset,
        limit=limit,
    )
    return ValidationLogList(
        logs=logs,
        total=total,
        offset=offset,
        limit=limit,
    )


# -- Review-time logging -----------------------------------------------------


@router.post(
    "/validation/fields/{field_id}/verify",
    response_model=ValidationLogRead,
    status_code=201,
    summary="Record a field verification",
    description=(
        "Records a FIELD_VERIFIED log entry for an extracted field on a task "
        "that is IN_REVIEW. The field itself is not modified; field corrections "
        "are owned by the human verification module."
    ),
    responses={
        400: _ERROR_RESPONSES[400],
        404: _ERROR_RESPONSES[404],
        422: _ERROR_RESPONSES[422],
        500: _ERROR_RESPONSES[500],
    },
)
@_handle_validation_errors
def verify_field(
    field_id: int,
    request: FieldVerifyRequest,
    db: _GET_DB,
) -> ValidationLogRead:
    """Record a field verification event."""
    return _log_service(db).record_field_verification(
        task_id=request.validation_task_id,
        field_id=field_id,
        result=request.result,
        comment=request.comment,
    )


@router.post(
    "/validation/fields/{field_id}/correct",
    response_model=ValidationLogRead,
    status_code=201,
    summary="Record a field correction",
    description=(
        "Records a FIELD_CORRECTED log entry for an extracted field on a task "
        "that is IN_REVIEW. The original extracted value is preserved in the log "
        "as previous_value. The field row itself is not modified; persistent "
        "corrections are owned by the human verification module."
    ),
    responses={
        400: _ERROR_RESPONSES[400],
        404: _ERROR_RESPONSES[404],
        422: _ERROR_RESPONSES[422],
        500: _ERROR_RESPONSES[500],
    },
)
@_handle_validation_errors
def correct_field(
    field_id: int,
    request: FieldCorrectRequest,
    db: _GET_DB,
) -> ValidationLogRead:
    """Record a field correction event."""
    return _log_service(db).record_field_correction(
        task_id=request.validation_task_id,
        field_id=field_id,
        corrected_value=request.corrected_value,
        reason=request.reason,
    )


@router.post(
    "/validation/evidence/{evidence_id}/review",
    response_model=ValidationLogRead,
    status_code=201,
    summary="Record a signature/stamp evidence review",
    description=(
        "Records a SIGNATURE_REVIEWED or STAMP_REVIEWED log entry for a visual "
        "detection row on a task that is IN_REVIEW. Presence detection is "
        "reported as-is; it does not claim authenticity."
    ),
    responses={
        400: _ERROR_RESPONSES[400],
        404: _ERROR_RESPONSES[404],
        422: _ERROR_RESPONSES[422],
        500: _ERROR_RESPONSES[500],
    },
)
@_handle_validation_errors
def review_evidence(
    evidence_id: int,
    request: EvidenceReviewRequest,
    db: _GET_DB,
) -> ValidationLogRead:
    """Record a signature/stamp evidence review event."""
    return _log_service(db).record_evidence_review(
        task_id=request.validation_task_id,
        evidence_id=evidence_id,
        result=request.result,
        comment=request.comment,
    )
