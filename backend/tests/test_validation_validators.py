"""Unit tests for the pure validation helpers.

These tests need no database: they exercise the task state machine, the
mandatory-reason rule, the IN_REVIEW guard and the check-type / evidence action
mappings that the services rely on.
"""

import pytest

from app.database.models.enums import (
    ValidationLogAction,
    ValidationLogCheckType,
    ValidationLogResult,
    ValidationTaskStatus,
)
from app.validation.exceptions import (
    InvalidValidationState,
    MissingReason,
    ValidationAlreadyCompleted,
    ValidationAlreadyRejected,
    ValidationAlreadyStarted,
    ValidationTaskNotReady,
)
from app.validation.validators import (
    ensure_transition,
    require_reason,
    require_task_in_review,
)
from app.validation.services import check_type_for_field, evidence_action_for

PENDING = ValidationTaskStatus.PENDING
IN_REVIEW = ValidationTaskStatus.IN_REVIEW
NEEDS_CORRECTION = ValidationTaskStatus.NEEDS_CORRECTION
VALIDATED = ValidationTaskStatus.VALIDATED
REJECTED = ValidationTaskStatus.REJECTED


# --- State transitions ------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (PENDING, IN_REVIEW),
        (IN_REVIEW, VALIDATED),
        (IN_REVIEW, REJECTED),
        (IN_REVIEW, NEEDS_CORRECTION),
    ],
)
def test_legal_transitions(current, target):
    ensure_transition(current, target)


def test_start_after_start_is_rejected():
    with pytest.raises(ValidationAlreadyStarted):
        ensure_transition(IN_REVIEW, IN_REVIEW)


def test_complete_before_start_is_not_ready():
    with pytest.raises(ValidationTaskNotReady):
        ensure_transition(PENDING, VALIDATED)


def test_reject_before_start_is_not_ready():
    with pytest.raises(ValidationTaskNotReady):
        ensure_transition(PENDING, REJECTED)


def test_correction_before_start_is_not_ready():
    with pytest.raises(ValidationTaskNotReady):
        ensure_transition(PENDING, NEEDS_CORRECTION)


def test_complete_after_complete_is_rejected():
    with pytest.raises(ValidationAlreadyCompleted):
        ensure_transition(VALIDATED, VALIDATED)


def test_actions_after_complete_are_rejected():
    with pytest.raises(ValidationAlreadyCompleted):
        ensure_transition(VALIDATED, NEEDS_CORRECTION)


def test_reject_after_reject_is_rejected():
    with pytest.raises(ValidationAlreadyRejected):
        ensure_transition(REJECTED, REJECTED)


def test_actions_after_reject_are_rejected():
    with pytest.raises(ValidationAlreadyRejected):
        ensure_transition(REJECTED, VALIDATED)


def test_corrected_task_is_terminal():
    with pytest.raises(InvalidValidationState):
        ensure_transition(NEEDS_CORRECTION, IN_REVIEW)


# --- Reason -----------------------------------------------------------------


def test_require_reason_returns_trimmed():
    assert require_reason("  a reason  ") == "a reason"


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_require_reason_missing(reason):
    with pytest.raises(MissingReason):
        require_reason(reason)


# --- IN_REVIEW guard --------------------------------------------------------


def test_require_review_allows_in_review():
    require_task_in_review(IN_REVIEW)


@pytest.mark.parametrize("status", [PENDING, NEEDS_CORRECTION, VALIDATED, REJECTED])
def test_require_review_rejects_non_review(status):
    with pytest.raises(ValidationTaskNotReady):
        require_task_in_review(status)


# --- Check type / evidence mapping ------------------------------------------


@pytest.mark.parametrize(
    ("field_name", "expected"),
    [
        ("account_number", ValidationLogCheckType.ACCOUNT_NUMBER),
        ("bank_account_number", ValidationLogCheckType.ACCOUNT_NUMBER),
        ("ntn", ValidationLogCheckType.NTN),
        ("bank_name", ValidationLogCheckType.BANK_NAME),
        ("account_title", ValidationLogCheckType.ACCOUNT_TITLE),
        ("applicant_name", ValidationLogCheckType.GENERAL),
    ],
)
def test_check_type_for_field(field_name, expected):
    assert check_type_for_field(field_name) is expected


def test_evidence_action_signature():
    assert evidence_action_for("SIGNATURE") == (
        ValidationLogAction.SIGNATURE_REVIEWED,
        ValidationLogCheckType.SIGNATURE,
    )


def test_evidence_action_stamp():
    assert evidence_action_for("stamp") == (
        ValidationLogAction.STAMP_REVIEWED,
        ValidationLogCheckType.STAMP,
    )


def test_evidence_action_unknown_is_document_review():
    assert evidence_action_for("QR_CODE") == (
        ValidationLogAction.DOCUMENT_REVIEWED,
        ValidationLogCheckType.DOCUMENT_REVIEW,
    )
