"""Tests for the normalization API and end-to-end normalization flow.

End-to-end tests exercise the full chain through the real API: upload, technical
validation, document processing, analysis, confidence evaluation and (where the
scenario needs it) human review, then normalization. Digital PDFs carry their
analysis text directly; scanned images use the deterministic fake OCR engine so
no PaddleOCR model is required.
"""

from tests.test_confidence_api import (
    add_digital_statement,
    add_scanned_statement,
    audit_actions,
    evaluate,
    review,
    stored_fields,
)
from tests.test_document_analysis_api import (
    PAYSLIP_TEXT,
    add_digital_pdf,
    analyze_documents,
    run_processing,
)
from tests.test_technical_validation_api import create_application

API = "/api/v1"

NORMALIZE_URL = "/normalize"
NORMALIZED_FIELDS_URL = "/normalized-fields"

NORMALIZATION_VERSION = "1.0.0"


def add_digital_payslip(client, storage_root) -> int:
    """Upload + validate + process + analyze a digital payslip; return its id."""
    application_id = create_application(client)
    add_digital_pdf(storage_root, application_id, PAYSLIP_TEXT)
    run_processing(client, application_id)
    analyze_documents(client, application_id)
    return application_id


def normalize(client, application_id: int) -> dict:
    """Call the normalize endpoint and return the JSON response."""
    response = client.post(f"{API}/applications/{application_id}{NORMALIZE_URL}")
    assert response.status_code == 200, response.text
    return response.json()


def get_normalized_fields(client, application_id: int) -> list[dict]:
    """Call the normalized-fields endpoint and return the JSON response."""
    response = client.get(f"{API}/applications/{application_id}{NORMALIZED_FIELDS_URL}")
    assert response.status_code == 200, response.text
    return response.json()


def items_by_field(response: dict) -> dict[str, dict]:
    """Return the per-field normalization items keyed on the field name."""
    return {item["field_name"]: item for item in response["items"]}


def _decisions(decisions: list[tuple[str, str, str | None]]) -> list[dict]:
    """Build review decision payloads as (field_name, decision, corrected_value)."""
    return [
        {
            "field_name": name,
            "decision": decision,
            **({"corrected_value": value} if value is not None else {}),
        }
        for name, decision, value in decisions
    ]


# --- Digital high-confidence flow --------------------------------------------


def test_normalize_digital_statement(client, storage_root):
    application_id = add_digital_statement(client, storage_root)
    assert evaluate(client, application_id)["processing_status"] == "READY_FOR_NORMALIZATION"

    result = normalize(client, application_id)

    assert result["application_id"] == application_id
    assert result["processing_status"] == "READY_FOR_BUSINESS_VALIDATION"
    assert result["normalization_version"] == NORMALIZATION_VERSION
    assert result["summary"] == {
        "total": 11,
        "normalized": 11,
        "skipped": 0,
        "failed": 0,
    }

    items = items_by_field(result)
    assert items["iban"]["normalized_value"] == "DE89370400440532013000"
    assert items["account_number"]["normalized_value"] == "1234567890"
    assert items["account_holder"]["normalized_value"] == "JOHN A. DOE"
    assert items["bank_name"]["normalized_value"] == "SPARKASSE"
    assert items["statement_period"]["normalized_value"] == "2026-01-01 - 2026-01-31"
    assert items["iban"]["normalizer"] == "iban"
    assert items["statement_period"]["normalizer"] == "statement_period"
    assert all(item["status"] == "NORMALIZED" for item in result["items"])


def test_normalize_digital_payslip(client, storage_root):
    application_id = add_digital_payslip(client, storage_root)
    evaluate(client, application_id)

    result = normalize(client, application_id)

    items = items_by_field(result)
    assert items["employee_name"]["normalized_value"] == "JANE Q. ROE"
    assert items["employer_name"]["normalized_value"] == "ACME CORP GMBH"
    assert items["employee_id"]["normalized_value"] == "EMP-1001"
    assert items["salary_month"]["normalized_value"] == "2026-01"
    assert items["payment_date"]["normalized_value"] == "2026-01-31"
    assert result["summary"]["total"] == 7


def test_normalize_persists_normalized_value(client, storage_root):
    application_id = add_digital_statement(client, storage_root)
    evaluate(client, application_id)
    normalize(client, application_id)

    fields = stored_fields(application_id)
    assert fields["iban"].normalized_value == "DE89370400440532013000"
    assert fields["account_holder"].normalized_value == "JOHN A. DOE"
    assert fields["statement_period"].normalized_value == "2026-01-01 - 2026-01-31"


# --- Human review flow -------------------------------------------------------


def test_normalize_skips_unverified_fields(client, storage_root, monkeypatch):
    application_id = add_scanned_statement(client, storage_root, monkeypatch)
    flagged = evaluate(client, application_id)["fields_requiring_review"]
    decisions = [
        (field["field_name"], "VERIFIED", None)
        for field in flagged
        if field["field_name"] != "iban"
    ]
    decisions.append(("iban", "CANNOT_VERIFY", None))
    assert review(client, application_id, _decisions(decisions))["processing_status"] == (
        "PROCESSING_HALTED"
    )

    result = normalize(client, application_id)

    items = items_by_field(result)
    assert items["iban"]["status"] == "SKIPPED"
    assert items["iban"]["reason"] == "not verified: CANNOT_VERIFY"
    assert items["iban"]["normalized_value"] is None
    assert result["summary"]["skipped"] == 1
    assert result["summary"]["normalized"] == 10

    fields = stored_fields(application_id)
    assert fields["iban"].verification_status == "CANNOT_VERIFY"
    assert fields["account_holder"].normalized_value == "JOHN A. DOE"


def test_normalize_prefers_human_corrected_value(client, storage_root, monkeypatch):
    application_id = add_scanned_statement(client, storage_root, monkeypatch)
    flagged = evaluate(client, application_id)["fields_requiring_review"]
    decisions = [
        (field["field_name"], "VERIFIED", None)
        for field in flagged
        if field["field_name"] != "iban"
    ]
    decisions.append(("iban", "CORRECTED", "de89 3704 0044 0532 0130 00"))
    assert review(client, application_id, _decisions(decisions))["processing_status"] == (
        "READY_FOR_NORMALIZATION"
    )

    result = normalize(client, application_id)

    items = items_by_field(result)
    assert items["iban"]["source_value"] == "de89 3704 0044 0532 0130 00"
    assert items["iban"]["normalized_value"] == "DE89370400440532013000"
    assert items["iban"]["status"] == "NORMALIZED"
    assert result["summary"]["normalized"] == 11

    fields = stored_fields(application_id)
    assert fields["iban"].human_corrected_value == "de89 3704 0044 0532 0130 00"
    assert fields["iban"].normalized_value == "DE89370400440532013000"


# --- Idempotency -------------------------------------------------------------


def test_normalize_is_idempotent(client, storage_root):
    application_id = add_digital_statement(client, storage_root)
    evaluate(client, application_id)

    first = normalize(client, application_id)
    second = normalize(client, application_id)

    assert first["summary"] == second["summary"] == {
        "total": 11,
        "normalized": 11,
        "skipped": 0,
        "failed": 0,
    }
    assert [
        item["normalized_value"] for item in first["items"]
    ] == [item["normalized_value"] for item in second["items"]]


# --- Read endpoint -----------------------------------------------------------


def test_get_normalized_fields_returns_stored_values(client, storage_root):
    application_id = add_digital_statement(client, storage_root)
    evaluate(client, application_id)
    normalize(client, application_id)

    records = get_normalized_fields(client, application_id)

    by_name = {record["field_name"]: record for record in records}
    assert len(records) == 11
    assert by_name["iban"]["normalized_value"] == "DE89370400440532013000"
    assert by_name["account_holder"]["normalized_value"] == "JOHN A. DOE"
    assert by_name["account_holder"]["verification_status"] == "AUTO_VERIFIED"
    assert all(record["extracted_value"] for record in records)


# --- Audit -------------------------------------------------------------------


def test_normalization_is_audited(client, storage_root):
    application_id = add_digital_statement(client, storage_root)
    evaluate(client, application_id)
    normalize(client, application_id)

    actions = audit_actions(application_id)
    assert "normalization.completed" in actions
    assert actions.count("normalization.completed") == 1


# --- Error paths -------------------------------------------------------------


def test_normalize_application_not_found(client):
    response = client.post(f"{API}/applications/999999{NORMALIZE_URL}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found"


def test_normalize_no_extracted_fields(client):
    application_id = create_application(client)
    response = client.post(f"{API}/applications/{application_id}{NORMALIZE_URL}")
    assert response.status_code == 422
    assert "extracted fields" in response.json()["detail"].lower()


def test_get_normalized_fields_no_extracted_fields(client):
    application_id = create_application(client)
    response = client.get(f"{API}/applications/{application_id}{NORMALIZED_FIELDS_URL}")
    assert response.status_code == 422
    assert "extracted fields" in response.json()["detail"].lower()
