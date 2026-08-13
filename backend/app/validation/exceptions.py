"""Domain exceptions for the validation module.

Every exception carries an HTTP status code and a human-readable detail; the
module's routes translate them into ``HTTPException`` responses via the shared
``_handle_validation_errors`` decorator.
"""


class ValidationError(Exception):
    """Base class for every validation module error.

    Attributes:
        status_code: HTTP status code used for the error response.
        detail: Human-readable description returned to the client.
    """

    status_code: int = 500
    detail: str = "Validation failed"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class ValidationTaskNotFound(ValidationError):
    """The referenced validation task does not exist."""

    status_code = 404
    detail = "Validation task not found"


class ValidationApplicationNotFound(ValidationError):
    """The referenced application does not exist."""

    status_code = 404
    detail = "Application not found"


class ValidationFieldNotFound(ValidationError):
    """The referenced extracted field does not exist."""

    status_code = 404
    detail = "Extracted field not found"


class ValidationEvidenceNotFound(ValidationError):
    """The referenced evidence (visual detection) does not exist."""

    status_code = 404
    detail = "Evidence not found"


class InvalidValidationState(ValidationError):
    """The requested transition is not allowed for the current state."""

    status_code = 409
    detail = "Invalid validation state transition"


class ValidationAlreadyStarted(ValidationError):
    """The task has already left the PENDING state and cannot be started again."""

    status_code = 409
    detail = "Validation task has already been started"


class ValidationAlreadyCompleted(ValidationError):
    """The task has already reached a terminal state and cannot be completed."""

    status_code = 409
    detail = "Validation task has already been completed"


class ValidationAlreadyRejected(ValidationError):
    """The task has already reached a terminal state and cannot be rejected."""

    status_code = 409
    detail = "Validation task has already been rejected"


class ValidationTaskNotReady(ValidationError):
    """An action requires the task to be IN_REVIEW first."""

    status_code = 400
    detail = "Validation task has not been started"


class MissingReason(ValidationError):
    """A rejection or correction request requires a mandatory reason."""

    status_code = 422
    detail = "A reason is required for this action"


class ValidationTaskCreationError(ValidationError):
    """The validation task could not be created."""

    status_code = 500
    detail = "Validation task could not be created"


class ValidationLogCreationError(ValidationError):
    """The validation state could not be persisted with its log entry."""

    status_code = 500
    detail = "Validation log could not be created"


__all__ = [
    "InvalidValidationState",
    "MissingReason",
    "ValidationAlreadyCompleted",
    "ValidationAlreadyRejected",
    "ValidationAlreadyStarted",
    "ValidationApplicationNotFound",
    "ValidationError",
    "ValidationEvidenceNotFound",
    "ValidationFieldNotFound",
    "ValidationLogCreationError",
    "ValidationTaskCreationError",
    "ValidationTaskNotFound",
    "ValidationTaskNotReady",
]
