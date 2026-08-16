"""Tests for the validation report API.

End-to-end tests build complete applications through the real API -- upload,
processing, analysis, confidence evaluation, normalization and business rule
validation -- and then check the read-only report endpoints. The report must
never run rules or detections itself and must never write to the database.
"""

from app.database.connection import SessionLocal
from app.database.models.enums import ApplicationStatus, DocumentType
from app.database.repositories.application_repository import ApplicationRepository
from app.reports.constants import REPORT_GROUP_ORDER, VISUAL_TYPE_BY_RULE
from app.rule_engine.constants import REQUIRED_DOCUMENT_TYPES
from tests.test_confidence_api import add_digital_statement, evaluate
from tests.test_document_analysis_api import (
    AUTHORITY_LETTER_TEXT,
    BANK_STATEMENT_TEXT,
    add_digital_pdf,
    analyze_documents,
    run_processing,
)
from tests.test_normalization_api import normalize
from tests.test_rule_engine_api import (
    BILATERAL_STATEMENT_TEXT,
    add_visual_detection,
    document_ids_by_type,
    validate,
)
from tests.test_technical_validation_api import create_application

API = "/api/v1"

REPORT_URL = "/validation-report"
HTML_URL = "/validation-report/html"
SUMMARY_URL = "/validation-summary"

REPORT_VERSION = "1.0.0"

#: Per-group rule totals expected from the 49-rule ruleset (50 implemented,
#: CrossPeriodRule unregistered -- see rule_engine/rules/__init__.py).
EXPECTED_GROUP_TOTALS = {
    "Document Validation": 14,
    "Format Validation": 6,
    # CrossPeriodRule is unregistered (see rule_engine/rules/__init__.py) --
    # 3 of the 4 implemented cross-document rules are active.
    "Cross Document Validation": 3,
    "Date Validation": 7,
    "Signature Validation": 6,
    "Stamp Validation": 5,
    "Business Policy Validation": 4,
    "Quality Validation": 4,
}


def build_full_application(client, storage_root, *, with_detections: bool) -> int:
    """Build an application carrying all eight required documents, analysed.

    BILATERAL_AGREEMENT and AUTHORITY_LETTER each get their own real-shaped
    text (Phase 1, docs/IMPLEMENTATION_ROADMAP.md gave both real extractors).
    BILATERAL_AGREEMENT's text carries the same account_holder/account_number/
    iban values as BANK_STATEMENT_TEXT, so the cross-document consistency
    rules still agree; AUTHORITY_LETTER's CRITICAL_FIELDS are all non-bank
    fields (focal_person_name/designation/organization_name -- see
    AuthorityLetterExtractor's docstring), so no cross-document account value
    needs to line up. Every other required type still has no real extractor
    and keeps using BANK_STATEMENT_TEXT via the generic keyword-based
    classifier, unaffected by either change.
    """
    application_id = create_application(client)
    for document_type in REQUIRED_DOCUMENT_TYPES:
        if document_type is DocumentType.BILATERAL_AGREEMENT:
            text = BILATERAL_STATEMENT_TEXT
        elif document_type is DocumentType.AUTHORITY_LETTER:
            text = AUTHORITY_LETTER_TEXT
        else:
            text = BANK_STATEMENT_TEXT
        add_digital_pdf(
            storage_root,
            application_id,
            text,
            document_type=document_type,
            filename=f"{document_type.value}.pdf",
        )
    run_processing(client, application_id)
    analyze_documents(client, application_id)
    evaluate(client, application_id)
    normalize(client, application_id)
    validate(client, application_id)
    if with_detections:
        document_ids = document_ids_by_type(application_id)
        for rule_id, document_type in VISUAL_TYPE_BY_RULE.items():
            add_visual_detection(
                document_id=document_ids[document_type],
                detection_type=rule_id.split("_")[1],
                is_present=True,
                confidence=1.0,
            )
        validate(client, application_id)
    return application_id


def build_single_statement_application(client, storage_root) -> int:
    """Build a minimal analysed application with rule results."""
    application_id = add_digital_statement(client, storage_root)
    evaluate(client, application_id)
    normalize(client, application_id)
    validate(client, application_id)
    return application_id


def get_report(client, application_id: int, *, url: str = REPORT_URL):
    """GET a report endpoint and return the response."""
    return client.get(f"{API}/applications/{application_id}{url}")


# --- Overall statuses --------------------------------------------------------


def test_report_approved_application(authenticated_client, storage_root):
    application_id = build_full_application(authenticated_client, storage_root, with_detections=True)

    response = get_report(authenticated_client, application_id)

    assert response.status_code == 200
    report = response.json()
    assert report["application_id"] == application_id
    assert report["report_version"] == REPORT_VERSION
    assert report["overall_status"] == "APPROVED"
    assert report["application"]["status"] == "SUBMITTED"
    assert report["application"]["created_by"] == "Test Operator"
    assert len(report["document_summary"]) == 8

    summary = report["rule_summary"]
    assert summary["total"] == 49
    assert summary["failed"] == 0
    assert summary["pending_manual_review"] == 0
    assert summary["passed"] + summary["warnings"] == 49

    assert [
        group["category"] for group in summary["by_category"]
    ] == list(REPORT_GROUP_ORDER)
    for group in summary["by_category"]:
        assert group["total"] == EXPECTED_GROUP_TOTALS[group["category"]]

    visual = report["visual_detection_summary"]
    assert visual["documents_checked"] == 6
    assert visual["signature_detected"] == 6
    assert visual["stamp_detected"] == 5
    assert visual["signature_missing"] == 0
    assert visual["stamp_missing"] == 0
    assert visual["average_confidence"] == 1.0

    extraction = report["extraction_summary"]
    assert extraction["total_fields"] > 0
    assert extraction["auto_verified"] == extraction["total_fields"]
    # AUTHORITY_LETTER's EXPECTED_FIELDS includes account_holder/account_number/
    # iban, which real Authority Letters never carry (see AuthorityLetterExtractor's
    # docstring) -- its template coverage is honestly 0.5, pulling the fleet-wide
    # mean confidence just under 1.0.
    assert extraction["overall_confidence"] == 0.9926

    assert [item["code"] for item in report["recommendations"]] == [
        "NO_ACTION_REQUIRED"
    ]


def test_report_failed_application(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)

    report = get_report(authenticated_client, application_id).json()

    assert report["overall_status"] == "FAILED"
    summary = report["rule_summary"]
    assert summary["total"] == 49
    assert summary["failed"] > 0
    # Only the present AMC document's visual rules await detection; the rest
    # fail because their documents are missing.
    assert summary["pending_manual_review"] == 2
    assert len(summary["by_category"]) == 8

    codes = [item["code"] for item in report["recommendations"]]
    assert "MISSING_REQUIRED_DOCUMENT" in codes
    assert "COMPLETE_PENDING_REVIEW" in codes
    assert "NO_ACTION_REQUIRED" not in codes

    visual = report["visual_detection_summary"]
    assert visual["documents_checked"] == 0
    assert visual["signature_detected"] == 0
    assert visual["stamp_missing"] == 0


def test_report_manual_review_required_application(authenticated_client, storage_root):
    application_id = build_full_application(
        authenticated_client, storage_root, with_detections=False
    )

    report = get_report(authenticated_client, application_id).json()

    assert report["overall_status"] == "MANUAL_REVIEW_REQUIRED"
    summary = report["rule_summary"]
    assert summary["failed"] == 0
    assert summary["pending_manual_review"] == 11
    codes = [item["code"] for item in report["recommendations"]]
    assert "COMPLETE_PENDING_REVIEW" in codes
    assert "NO_ACTION_REQUIRED" not in codes


def test_report_rejected_application_overrides_status(authenticated_client, storage_root):
    application_id = build_full_application(authenticated_client, storage_root, with_detections=True)
    db = SessionLocal()
    try:
        repository = ApplicationRepository(db)
        application = repository.get_by_id(application_id)
        repository.update(application, status=ApplicationStatus.REJECTED)
    finally:
        db.close()

    report = get_report(authenticated_client, application_id).json()

    assert report["overall_status"] == "REJECTED"
    assert report["application"]["status"] == "REJECTED"


# --- Report variants ---------------------------------------------------------


def test_report_summary_condensed(authenticated_client, storage_root):
    application_id = build_full_application(authenticated_client, storage_root, with_detections=True)

    response = get_report(authenticated_client, application_id, url=SUMMARY_URL)

    assert response.status_code == 200
    summary = response.json()
    assert summary["application_id"] == application_id
    assert summary["report_version"] == REPORT_VERSION
    assert summary["overall_status"] == "APPROVED"
    assert summary["application_status"] == "SUBMITTED"
    assert summary["document_count"] == 8
    assert summary["rule_total"] == 49
    assert summary["rule_passed"] + summary["rule_warnings"] == 49
    assert summary["rule_failed"] == 0
    assert summary["rule_pending_review"] == 0
    assert summary["field_count"] > 0
    # See test_report_approved_application's overall_confidence comment.
    assert summary["overall_confidence"] == 0.9926
    assert summary["recommendation_count"] == 1


def test_report_html_is_printable(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)

    response = get_report(authenticated_client, application_id, url=HTML_URL)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert "Validation Report" in html
    assert "Overall Status:" in html
    assert str(application_id) in html
    for group in REPORT_GROUP_ORDER:
        assert group in html


def test_report_is_idempotent(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)

    first = get_report(authenticated_client, application_id).json()
    second = get_report(authenticated_client, application_id).json()

    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second


# --- Error paths -------------------------------------------------------------


def test_report_missing_validation_results_rejected(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)

    for url in (REPORT_URL, HTML_URL, SUMMARY_URL):
        response = get_report(authenticated_client, application_id, url=url)
        assert response.status_code == 422
        assert "No validation results" in response.json()["detail"]


def test_report_technical_results_alone_rejected(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_digital_pdf(storage_root, application_id, BANK_STATEMENT_TEXT)
    run_processing(authenticated_client, application_id)

    response = get_report(authenticated_client, application_id)

    assert response.status_code == 422
    assert "No validation results" in response.json()["detail"]


def test_report_endpoints_application_not_found(authenticated_client):
    for url in (REPORT_URL, HTML_URL, SUMMARY_URL):
        response = get_report(authenticated_client, 999999, url=url)
        assert response.status_code == 404
        assert response.json()["detail"] == "Application not found"


