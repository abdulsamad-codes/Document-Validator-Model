"""Validation module.

Implements the validation workflow on top of the existing pipeline outputs
(rule engine results, extracted fields, visual detections): validation tasks
are created with versioned runs, driven through their lifecycle (start,
complete, reject, request-correction) and every important event is recorded on
an immutable validation log. No user/operator functionality lives here -- the
separate User/Operator module attaches authentication, roles and separation of
duties later.
"""

from app.validation.constants import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    MODULE_VERSION,
    TRANSITIONS,
)
from app.validation.exceptions import (
    InvalidValidationState,
    MissingReason,
    ValidationAlreadyCompleted,
    ValidationAlreadyRejected,
    ValidationAlreadyStarted,
    ValidationApplicationNotFound,
    ValidationError,
    ValidationEvidenceNotFound,
    ValidationFieldNotFound,
    ValidationLogCreationError,
    ValidationTaskCreationError,
    ValidationTaskNotFound,
    ValidationTaskNotReady,
)
from app.validation.routes import router
from app.validation.services import (
    ValidationLogService,
    ValidationTaskService,
    check_type_for_field,
    evidence_action_for,
)
from app.validation.validators import (
    ensure_transition,
    require_reason,
    require_task_in_review,
)

__all__ = [
    "DEFAULT_PAGE_LIMIT",
    "InvalidValidationState",
    "MAX_PAGE_LIMIT",
    "MODULE_VERSION",
    "MissingReason",
    "TRANSITIONS",
    "ValidationAlreadyCompleted",
    "ValidationAlreadyRejected",
    "ValidationAlreadyStarted",
    "ValidationApplicationNotFound",
    "ValidationError",
    "ValidationEvidenceNotFound",
    "ValidationFieldNotFound",
    "ValidationLogCreationError",
    "ValidationLogService",
    "ValidationTaskCreationError",
    "ValidationTaskNotFound",
    "ValidationTaskNotReady",
    "ValidationTaskService",
    "check_type_for_field",
    "ensure_transition",
    "evidence_action_for",
    "require_reason",
    "require_task_in_review",
    "router",
]
