"""Configuration for the validation module.

Centralizes the module version, the legal task state transitions and the
default pagination bounds. The transition map is the single source of truth for
the validation workflow; the service consults it (via ``app.validation.
validators``) before every state change.
"""

from app.database.models.enums import ValidationTaskStatus

#: Version of the validation workflow logic. Bumped whenever the transition
#: rules, the log vocabulary or the persistence behaviour changes so a stored
#: task/log can be traced to the exact logic that produced it.
MODULE_VERSION: str = "1.0.0"

#: Legal state transitions for a validation task. A task starts PENDING, moves
#: to IN_REVIEW and then reaches a terminal state (VALIDATED, REJECTED) or is
#: returned for correction (NEEDS_CORRECTION). NEEDS_CORRECTION is terminal for
#: the current run: corrected documents produce a brand new task/run instead of
#: reopening this one, so the historical result is never overwritten.
TRANSITIONS: dict[ValidationTaskStatus, tuple[ValidationTaskStatus, ...]] = {
    ValidationTaskStatus.PENDING: (ValidationTaskStatus.IN_REVIEW,),
    ValidationTaskStatus.IN_REVIEW: (
        ValidationTaskStatus.VALIDATED,
        ValidationTaskStatus.REJECTED,
        ValidationTaskStatus.NEEDS_CORRECTION,
    ),
    ValidationTaskStatus.NEEDS_CORRECTION: (),
    ValidationTaskStatus.VALIDATED: (),
    ValidationTaskStatus.REJECTED: (),
}

#: Default number of rows returned when no limit is provided.
DEFAULT_PAGE_LIMIT: int = 50

#: Hard upper bound for pagination limits.
MAX_PAGE_LIMIT: int = 200


__all__ = [
    "DEFAULT_PAGE_LIMIT",
    "MAX_PAGE_LIMIT",
    "MODULE_VERSION",
    "TRANSITIONS",
]
