"""Tests for the business rule engine API and end-to-end validation flow.

End-to-end tests exercise the full chain through the real API: upload, document
processing, analysis, confidence evaluation, normalization and then business
rule validation. Visual detection outcomes are injected directly through the
repository, since the detection pipeline itself is external.
"""

from sqlalchemy import text

from app.database.connection import SessionLocal
from app.database.models.enums import DocumentType
from app.database.repositories.visual_detection_repository import (
    VisualDetectionRepository,
)
from tests.test_confidence_api import (
    add_digital_statement,
    add_scanned_statement,
    audit_actions,
    evaluate,
)
from tests.test_document_analysis_api import (
    BANK_STATEMENT_TEXT,
    add_digital_pdf,
    analyze_documents,
    run_processing,
)
from tests.test_normalization_api import normalize
from tests.test_technical_validation_api import (
    add_document,
    create_application,
    run_validation,
)

API = "/api/v1"

VALIDATE_URL = "/validate"
VALIDATION_RESULTS_URL = "/validation-results"

RULE_ENGINE_VERSION = "1.0.0"

#: A bank statement variant with a different account holder for cross-doc tests.
MISMATCH_STATEMENT_TEXT = BANK_STATEMENT_TEXT.replace(
    "Account Holder: John A. Doe",
    "Account Holder: John B. Smith",
)


def validate(client, application_id: int) -> dict:
    """Call the validate endpoint and return the JSON response."""
    response = client.post(f"{API}/applications/{application_id}{VALIDATE_URL}")
    assert response.status_code == 200, response.text
    return response.json()


def get_validation_results(client, application_id: int, category: str | None = None) -> dict:
    """Call the validation-results endpoint and return the JSON response."""
    url = f"{API}/applications/{application_id}{VALIDATION_RESULTS_URL}"
    if category:
        url += f"?category={category}"
    response = client.get(url)
    assert response.status_code == 200, response.text
    return response.json()


def add_statement_with_type(
    client,
    storage_root,
    application_id: int,
    *,
    document_type: DocumentType,
    text: str = BANK_STATEMENT_TEXT,
) -> int:
    """Add one analysed document of ``document_type`` to an application."""
    add_digital_pdf(storage_root, application_id, text, document_type=document_type)
    run_processing(client, application_id)
    analyze_documents(client, application_id)
    return application_id


def add_visual_detection(
    *,
    document_id: int,
    detection_type: str,
    is_present: bool,
    confidence: float | None = None,
) -> None:
    """Insert a visual detection outcome for a document."""
    db = SessionLocal()
    try:
        VisualDetectionRepository(db).upsert(
            document_id=document_id,
            detection_type=detection_type,
            is_present=is_present,
            confidence=confidence,
            detection_engine="test",
        )
    finally:
        db.close()


def document_ids_by_type(application_id: int) -> dict[str, int]:
    """Return the document id of each document type for an application."""
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT document_type, id FROM documents "
                "WHERE application_id = :application_id"
            ),
            {"application_id": application_id},
        ).all()
        return {row[0]: row[1] for row in rows}
    finally:
        db.close()


# --- Full chain ---------------------------------------------------------------


def test_validate_digital_statement_full_chain(client, storage_root):
    application_id = add_digital_statement(client, storage_root)
    evaluate(client, application_id)
    normalize(client, application_id)

    result = validate(client, application_id)

    assert result["application_id"] == application_id
    assert result["rule_engine_version"] == RULE_ENGINE_VERSION
    assert result["summary"]["total"] == 50
    assert len(result["category_summary"]) == 8

    by_rule = {item["rule_id"]: item for item in result["results"]}
    assert by_rule["DOC_AMC_PRESENT"]["status"] == "PASS"
    assert by_rule["DOC_TRIPARTITE_PRESENT"]["status"] == "FAIL"
    assert by_rule["DOC_BILATERAL_PRESENT"]["status"] == "FAIL"
    assert by_rule["FLD_IBAN_PRESENT"]["status"] == "PASS"
    assert by_rule["FLD_ACCOUNT_HOLDER_PRESENT"]["status"] == "PASS"
    assert by_rule["FLD_BALANCES_PRESENT"]["status"] == "PASS"
    assert by_rule["FMT_IBAN"]["status"] == "PASS"
    assert by_rule["FMT_ACCOUNT_NUMBER"]["status"] == "PASS"
    assert by_rule["FMT_AMOUNT"]["status"] == "PASS"
    assert by_rule["DATE_PERIOD_SEQUENCE"]["status"] == "PASS"
    assert by_rule["DATE_PERIOD_WITHIN_RANGE"]["status"] in ("PASS", "WARNING")
    assert by_rule["POL_BALANCE_RECONCILIATION"]["status"] == "PASS"
    assert by_rule["POL_SINGLE_CURRENCY"]["status"] == "PASS"
    assert by_rule["POL_ACCOUNT_HOLDER_REAL"]["status"] == "PASS"
    assert by_rule["QUAL_TRANSACTION_COUNT"]["status"] == "PASS"
    assert by_rule["VIS_SIGNATURE_AMC"]["status"] == "PENDING_MANUAL_REVIEW"
    assert by_rule["VIS_STAMP_AMC"]["status"] == "PENDING_MANUAL_REVIEW"
    assert by_rule["CROSS_ACCOUNT_HOLDER_MATCH"]["status"] == "FAIL"

    assert result["validation_status"] == "FAIL"


def test_validate_persists_rule_results(client, storage_root):
    application_id = add_digital_statement(client, storage_root)
    evaluate(client, application_id)
    normalize(client, application_id)
    validate(client, application_id)

    stored = get_validation_results(client, application_id)

    assert stored["application_id"] == application_id
    assert stored["total"] == 50
    by_rule = {item["rule_id"]: item for item in stored["results"]}
    assert by_rule["FMT_IBAN"]["status"] == "PASS"
    assert by_rule["FMT_IBAN"]["severity"] == "INFO"
    assert by_rule["DOC_TRIPARTITE_PRESENT"]["severity"] == "ERROR"
    assert by_rule["VIS_SIGNATURE_AMC"]["severity"] == "WARNING"
    assert by_rule["VIS_SIGNATURE_AMC"]["category_label"] == "Visual verification"
    assert by_rule["FLD_IBAN_PRESENT"]["related_field_names"] == ["iban"]
    assert by_rule["DOC_AMC_PRESENT"]["related_document_ids"]


def test_validate_is_idempotent_in_storage(client, storage_root):
    application_id = add_digital_statement(client, storage_root)
    evaluate(client, application_id)
    normalize(client, application_id)

    validate(client, application_id)
    first = get_validation_results(client, application_id)
    validate(client, application_id)
    second = get_validation_results(client, application_id)

    assert first["total"] == second["total"] == 50
    assert [item["rule_id"] for item in first["results"]] == [
        item["rule_id"] for item in second["results"]
    ]


def test_validate_is_audited(client, storage_root):
    application_id = add_digital_statement(client, storage_root)
    evaluate(client, application_id)
    normalize(client, application_id)
    validate(client, application_id)

    actions = audit_actions(application_id)
    assert actions.count("rule_engine.validated") == 1


def test_get_validation_results_excludes_technical_rows(client, storage_root):
    application_id = create_application(client)
    add_digital_pdf(storage_root, application_id, BANK_STATEMENT_TEXT)
    run_validation(client, application_id)
    run_processing(client, application_id)
    analyze_documents(client, application_id)
    evaluate(client, application_id)
    normalize(client, application_id)
    validate(client, application_id)

    stored = get_validation_results(client, application_id)
    assert stored["total"] == 50
    assert all(
        item["rule_category"] != "technical_validation" for item in stored["results"]
    )


def test_get_validation_results_filters_by_category(client, storage_root):
    application_id = add_digital_statement(client, storage_root)
    evaluate(client, application_id)
    normalize(client, application_id)
    validate(client, application_id)

    stored = get_validation_results(client, application_id, category="visual")

    assert stored["total"] == 11
    assert all(item["rule_category"] == "visual" for item in stored["results"])
    assert all(item["category_label"] == "Visual verification" for item in stored["results"])


# --- Visual detections -------------------------------------------------------


def test_validate_visual_rules_pass_with_detections(client, storage_root):
    application_id = add_digital_statement(client, storage_root)
    evaluate(client, application_id)
    normalize(client, application_id)
    amc_id = document_ids_by_type(application_id)["ACCOUNT_MAINTENANCE_CERTIFICATE"]
    add_visual_detection(document_id=amc_id, detection_type="SIGNATURE", is_present=True)
    add_visual_detection(document_id=amc_id, detection_type="STAMP", is_present=True)

    result = validate(client, application_id)

    by_rule = {item["rule_id"]: item for item in result["results"]}
    assert by_rule["VIS_SIGNATURE_AMC"]["status"] == "PASS"
    assert by_rule["VIS_STAMP_AMC"]["status"] == "PASS"


def test_validate_visual_rules_fail_when_absent(client, storage_root):
    application_id = add_digital_statement(client, storage_root)
    evaluate(client, application_id)
    normalize(client, application_id)
    amc_id = document_ids_by_type(application_id)["ACCOUNT_MAINTENANCE_CERTIFICATE"]
    add_visual_detection(document_id=amc_id, detection_type="SIGNATURE", is_present=False)

    result = validate(client, application_id)

    by_rule = {item["rule_id"]: item for item in result["results"]}
    assert by_rule["VIS_SIGNATURE_AMC"]["status"] == "FAIL"
    assert "not detected" in by_rule["VIS_SIGNATURE_AMC"]["message"]


# --- Cross-document consistency ----------------------------------------------


def test_validate_cross_document_rules_pass(client, storage_root):
    application_id = create_application(client)
    add_statement_with_type(
        client,
        storage_root,
        application_id,
        document_type=DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    add_statement_with_type(
        client,
        storage_root,
        application_id,
        document_type=DocumentType.BILATERAL_AGREEMENT,
    )
    add_statement_with_type(
        client,
        storage_root,
        application_id,
        document_type=DocumentType.TRIPARTITE_AGREEMENT,
    )
    evaluate(client, application_id)
    normalize(client, application_id)

    result = validate(client, application_id)

    by_rule = {item["rule_id"]: item for item in result["results"]}
    assert by_rule["CROSS_ACCOUNT_HOLDER_MATCH"]["status"] == "PASS"
    assert by_rule["CROSS_ACCOUNT_NUMBER_MATCH"]["status"] == "PASS"
    assert by_rule["CROSS_IBAN_MATCH"]["status"] == "PASS"
    assert by_rule["CROSS_PERIOD_MATCH"]["status"] == "PASS"
    assert by_rule["DOC_AMC_PRESENT"]["status"] == "PASS"
    assert by_rule["DOC_BILATERAL_PRESENT"]["status"] == "PASS"
    assert by_rule["DOC_TRIPARTITE_PRESENT"]["status"] == "PASS"


def test_validate_cross_document_rules_fail_on_mismatch(client, storage_root):
    application_id = create_application(client)
    add_statement_with_type(
        client,
        storage_root,
        application_id,
        document_type=DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    add_statement_with_type(
        client,
        storage_root,
        application_id,
        document_type=DocumentType.BILATERAL_AGREEMENT,
    )
    add_statement_with_type(
        client,
        storage_root,
        application_id,
        document_type=DocumentType.TRIPARTITE_AGREEMENT,
        text=MISMATCH_STATEMENT_TEXT,
    )
    evaluate(client, application_id)
    normalize(client, application_id)

    result = validate(client, application_id)

    by_rule = {item["rule_id"]: item for item in result["results"]}
    assert by_rule["CROSS_ACCOUNT_HOLDER_MATCH"]["status"] == "FAIL"
    assert "differs" in by_rule["CROSS_ACCOUNT_HOLDER_MATCH"]["message"]
    assert by_rule["CROSS_ACCOUNT_NUMBER_MATCH"]["status"] == "PASS"


# --- Pipeline robustness -----------------------------------------------------


def test_validate_runs_without_extracted_fields(client, storage_root):
    application_id = create_application(client)

    result = validate(client, application_id)

    assert result["summary"]["total"] == 50
    assert result["validation_status"] == "FAIL"
    by_rule = {item["rule_id"]: item for item in result["results"]}
    assert by_rule["DOC_AMC_PRESENT"]["status"] == "FAIL"
    assert by_rule["FLD_IBAN_PRESENT"]["status"] == "FAIL"


def test_validate_skipped_fields_warn(client, storage_root, monkeypatch):
    application_id = add_scanned_statement(client, storage_root, monkeypatch)
    flagged = evaluate(client, application_id)["fields_requiring_review"]
    decisions = [
        {"field_name": field["field_name"], "decision": "VERIFIED"}
        for field in flagged
        if field["field_name"] != "iban"
    ]
    decisions.append({"field_name": "iban", "decision": "CANNOT_VERIFY"})
    review_response = client.post(
        f"{API}/applications/{application_id}/confidence/review",
        json={"reviewer_name": "reviewer", "decisions": decisions},
    )
    assert review_response.status_code == 200, review_response.text
    normalize(client, application_id)

    result = validate(client, application_id)

    by_rule = {item["rule_id"]: item for item in result["results"]}
    assert by_rule["FLD_IBAN_PRESENT"]["status"] == "FAIL"
    assert by_rule["FMT_IBAN"]["status"] == "WARNING"


# --- Error paths -------------------------------------------------------------


def test_validate_application_not_found(client):
    response = client.post(f"{API}/applications/999999{VALIDATE_URL}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found"


def test_get_validation_results_application_not_found(client):
    response = client.get(f"{API}/applications/999999{VALIDATION_RESULTS_URL}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found"
