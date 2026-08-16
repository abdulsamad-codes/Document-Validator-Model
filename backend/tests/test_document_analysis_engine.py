"""Unit tests for the document analysis engine.

Covers document type detection, per-type field extraction, the reusable
validators, the cross-field consistency rules, the deterministic scoring and the
analysis repository. All fixtures are pure text, so no OCR engine or database
is needed except where explicitly noted.
"""

import pytest

from app.database.connection import SessionLocal
from app.database.models.enums import ApplicationStatus, DocumentType
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_analysis_repository import DocumentAnalysisRepository
from app.database.repositories.document_repository import DocumentRepository
from app.document_analysis.constants import (
    AnalyzedDocumentType,
    VerificationStatus,
)
from app.document_analysis.exceptions import UnsupportedDocumentType
from app.document_analysis.extractors import (
    _parse_amount,
    detect_document_type,
    extract_fields,
)
from app.document_analysis.rules import (
    RulesEngine,
    compute_score,
    compute_verification_status,
    scoring_components,
)
from app.document_analysis.validators import (
    ValidatorEngine,
    validate_account_number,
    validate_currency,
    validate_date,
    validate_date_not_future,
    validate_iban,
    validate_salary_month,
)

BANK_STATEMENT_TEXT = """MONTHLY ACCOUNT STATEMENT
Account Holder: John A. Doe
Account Number: 1234567890
IBAN: DE89370400440532013000
Bank: Sparkasse
Statement Period: 01/01/2026 - 31/01/2026
Opening Balance: 1,250.50
Closing Balance: 3,200.75
Total Credits: 2,500.00
Total Debits: 549.75
Currency: EUR
Transactions: 23
"""

PAYSLIP_TEXT = """PAYSLIP
Employee Name: Jane Q. Roe
Employee ID: EMP-1001
Employer Name: Acme Corp GmbH
Gross Salary: 5,000.00
Net Salary: 3,850.50
Salary Month: 2026-01
Payment Date: 2026-01-31
"""

ID_TEXT = """NATIONAL IDENTITY CARD
Full Name: Jose P. Garcia
Date of Birth: 1990-05-15
ID Number: 1234567890
Nationality: Spain
Issue Date: 2018-06-01
Expiry Date: 2028-06-01
"""

TAX_TEXT = """TAX RETURN SUMMARY
Taxpayer Name: Maria K. Novak
Tax Reference Number: TAX-2025-000123
Tax Year: 2025
Gross Income: 45,000.00
Total Tax: 9,800.00
Currency: EUR
"""

#: Synthetic (fabricated, non-real) fixture mirroring the structural pattern
#: docs/Master_Rules_Combined.md Section 7 describes for a Bilateral
#: Agreement -- department name, PayMin/Digital Muhasil/Paymere BCX platform
#: terminology, a Section 5.2 PKR transaction-charge line and a Section 6
#: account block. Never real extracted values.
BILATERAL_AGREEMENT_TEXT = """BILATERAL AGREEMENT
This Agreement is made between the Bank and the Department.
Department: Sample Regional Development Authority

Section 5 - Transaction Charges
Section 5.2: As per prevailing charges of 1-Link, PKR 15 per transaction, payable via PayMin.

Section 6 - Account Information
Account Title: Sample Regional Development Authority
Account Number: 9876543210
IBAN: DE89370400440532013000
Effective Date: 2026-01-15
"""

#: Synthetic (fabricated, non-real) fixtures mirroring the real prose-embedded
#: Authority Letter template confirmed on two independent real departments in
#: Confidential Data/ -- structurally near-identical wording, one using a
#: comma before the designation, the other parenthesizing it. Never real
#: extracted values.
AUTHORITY_LETTER_TEXT_COMMA_FORM = """AUTHORITY LETTER
It is hereby authorized that Mr. Naveed Khan, Deputy Director Administration \
(BPS-18) is authorized to deal with and conduct correspondence and matter \
related to 1-Link and the Khyber Pakhtunkhwa Information Technology Board \
(KPITB) on the behalf of Directorate.
"""

AUTHORITY_LETTER_TEXT_PAREN_FORM = """AUTHORITY LETTER
It is hereby authorized that Mr. Salman Raza (Assistant Finance Officer) \
Tehsil Municipal Administration Sample is authorized to deal with and \
conduct correspondence and matters related to 1-Link and the Khyber \
Pakhtunkhwa Information Technology Board (KPITB) on behalf of TMA Sample \
District.
"""


def _components(text: str):
    document_type = detect_document_type(text)
    fields = extract_fields(text, document_type)
    validations = ValidatorEngine().run(document_type, fields)
    consistency = RulesEngine().run(document_type, fields)
    return document_type, fields, validations, consistency


# --- Document type detection -------------------------------------------------


def test_detect_bank_statement():
    assert detect_document_type(BANK_STATEMENT_TEXT) is AnalyzedDocumentType.BANK_STATEMENT


def test_detect_payslip():
    assert detect_document_type(PAYSLIP_TEXT) is AnalyzedDocumentType.PAYSLIP


def test_detect_identity_document():
    assert detect_document_type(ID_TEXT) is AnalyzedDocumentType.ID_DOCUMENT


def test_detect_tax_document():
    assert detect_document_type(TAX_TEXT) is AnalyzedDocumentType.TAX_DOCUMENT


def test_detect_unknown_document():
    text = "This is a casual letter with no financial keywords whatsoever."
    assert detect_document_type(text) is AnalyzedDocumentType.UNKNOWN


def test_detection_is_case_insensitive():
    assert detect_document_type(BANK_STATEMENT_TEXT.lower()) is AnalyzedDocumentType.BANK_STATEMENT


# --- Field extraction --------------------------------------------------------


def test_extract_bank_statement_fields():
    fields = extract_fields(BANK_STATEMENT_TEXT, AnalyzedDocumentType.BANK_STATEMENT)
    assert fields["account_holder"] == "John A. Doe"
    assert fields["account_number"] == "1234567890"
    assert fields["iban"] == "DE89370400440532013000"
    assert fields["bank_name"] == "Sparkasse"
    assert fields["statement_period"] == {"start": "2026-01-01", "end": "2026-01-31"}
    assert fields["opening_balance"] == 1250.5
    assert fields["closing_balance"] == 3200.75
    assert fields["total_credits"] == 2500.0
    assert fields["total_debits"] == 549.75
    assert fields["currency"] == "EUR"
    assert fields["transaction_count"] == 23


def test_extract_payslip_fields():
    fields = extract_fields(PAYSLIP_TEXT, AnalyzedDocumentType.PAYSLIP)
    assert fields["employee_name"] == "Jane Q. Roe"
    assert fields["employee_id"] == "EMP-1001"
    assert fields["employer_name"] == "Acme Corp GmbH"
    assert fields["gross_salary"] == 5000.0
    assert fields["net_salary"] == 3850.5
    assert fields["salary_month"] == "2026-01"
    assert fields["payment_date"] == "2026-01-31"


def test_extract_identity_fields():
    fields = extract_fields(ID_TEXT, AnalyzedDocumentType.ID_DOCUMENT)
    assert fields["full_name"] == "Jose P. Garcia"
    assert fields["date_of_birth"] == "1990-05-15"
    assert fields["document_number"] == "1234567890"
    assert fields["nationality"] == "Spain"
    assert fields["issue_date"] == "2018-06-01"
    assert fields["expiry_date"] == "2028-06-01"


def test_extract_tax_fields():
    fields = extract_fields(TAX_TEXT, AnalyzedDocumentType.TAX_DOCUMENT)
    assert fields["taxpayer_name"] == "Maria K. Novak"
    assert fields["tax_reference_number"] == "TAX-2025-000123"
    assert fields["tax_year"] == 2025
    assert fields["gross_income"] == 45000.0
    assert fields["total_tax"] == 9800.0
    assert fields["currency"] == "EUR"


def test_extract_unknown_type_raises():
    with pytest.raises(UnsupportedDocumentType):
        extract_fields("some text", AnalyzedDocumentType.UNKNOWN)


def test_extract_bilateral_agreement_fields():
    fields = extract_fields(
        BILATERAL_AGREEMENT_TEXT, AnalyzedDocumentType.BILATERAL_AGREEMENT
    )
    assert fields["organization_name"] == "Sample Regional Development Authority"
    assert fields["platform_name"] == "PayMin"
    assert "PKR 15 per transaction" in fields["transaction_charges"]
    assert fields["account_holder"] == "Sample Regional Development Authority"
    assert fields["account_number"] == "9876543210"
    assert fields["iban"] == "DE89370400440532013000"
    assert fields["effective_date"] == "2026-01-15"


def test_bilateral_agreement_validators_and_scoring():
    document_type = AnalyzedDocumentType.BILATERAL_AGREEMENT
    fields = extract_fields(BILATERAL_AGREEMENT_TEXT, document_type)
    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result for result in validations}
    assert by_field["account_number"]["status"] == "valid"
    assert by_field["iban"]["status"] == "valid"
    assert by_field["effective_date"]["status"] == "valid"

    consistency = RulesEngine().run(document_type, fields)
    assert consistency == []  # no consistency rules registered yet for this type

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    assert score > 0.0
    assert status is not VerificationStatus.FAILED


def test_extract_authority_letter_fields_comma_form():
    fields = extract_fields(
        AUTHORITY_LETTER_TEXT_COMMA_FORM, AnalyzedDocumentType.AUTHORITY_LETTER
    )
    assert fields["focal_person_name"] == "Naveed Khan"
    assert fields["focal_person_designation"] == "Deputy Director Administration"
    assert fields["organization_name"] == "Directorate"


def test_extract_authority_letter_fields_paren_form():
    fields = extract_fields(
        AUTHORITY_LETTER_TEXT_PAREN_FORM, AnalyzedDocumentType.AUTHORITY_LETTER
    )
    assert fields["focal_person_name"] == "Salman Raza"
    assert fields["focal_person_designation"] == "Assistant Finance Officer"
    assert fields["organization_name"] == "TMA Sample District"


def test_authority_letter_validators_and_scoring():
    document_type = AnalyzedDocumentType.AUTHORITY_LETTER
    fields = extract_fields(AUTHORITY_LETTER_TEXT_COMMA_FORM, document_type)
    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result for result in validations}
    # No account fields in this real-shaped fixture -- must be reported
    # missing, not invalid, and must not force a critical failure (they are
    # deliberately not critical fields for this type).
    assert by_field["account_number"]["status"] == "missing"
    assert by_field["iban"]["status"] == "missing"

    consistency = RulesEngine().run(document_type, fields)
    assert consistency == []  # no consistency rules registered yet for this type

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    assert score > 0.0
    assert status is not VerificationStatus.FAILED


def test_parse_amount_variants():
    assert _parse_amount("1,250.50") == 1250.5
    assert _parse_amount("1.250,50") == 1250.5
    assert _parse_amount("2,500.00") == 2500.0
    assert _parse_amount("549.75") == 549.75
    assert _parse_amount("EUR 45,000.00") == 45000.0
    assert _parse_amount("1,000") == 1000.0
    assert _parse_amount("0.99") == 0.99
    assert _parse_amount("garbage") is None


# --- Validators --------------------------------------------------------------


def test_validate_iban_valid():
    status, message = validate_iban("DE89370400440532013000")
    assert status == "valid"
    assert "checksum passed" in message


def test_validate_iban_invalid_checksum():
    status, _ = validate_iban("DE89370400440532013001")
    assert status == "invalid"


def test_validate_iban_invalid_format():
    assert validate_iban("12")[0] == "invalid"
    assert validate_iban("DE00")[0] == "invalid"


def test_validate_currency():
    assert validate_currency("EUR")[0] == "valid"
    assert validate_currency("eur")[0] == "invalid"
    assert validate_currency("EURO")[0] == "invalid"


def test_validate_account_number():
    assert validate_account_number("1234567890")[0] == "valid"
    assert validate_account_number("12")[0] == "invalid"
    assert validate_account_number("1234 5678 90")[0] == "valid"


def test_validate_date_accepts_future_expiry():
    assert validate_date("2028-06-01")[0] == "valid"
    assert validate_date("not-a-date")[0] == "invalid"


def test_validate_date_not_future_rejects_future():
    assert validate_date_not_future("1990-05-15")[0] == "valid"
    assert validate_date_not_future("2099-01-01")[0] == "invalid"


def test_validate_salary_month():
    assert validate_salary_month("2026-01")[0] == "valid"
    assert validate_salary_month("2026-13")[0] == "invalid"
    assert validate_salary_month("01/2026")[0] == "invalid"


def test_validator_engine_reports_missing_fields():
    text = """BANK STATEMENT
    Account Number: 1234567890
    Closing Balance: 5,000.00
    """
    document_type, fields, validations, _ = _components(text)
    assert document_type is AnalyzedDocumentType.BANK_STATEMENT
    assert fields["account_number"] == "1234567890"
    statuses = {result["field"]: result["status"] for result in validations}
    assert statuses["account_holder"] == "missing"
    assert statuses["opening_balance"] == "missing"
    assert any(result["message"] == "Account holder missing" for result in validations)


# --- Consistency rules -------------------------------------------------------


def test_rule_reconciliation_passes_with_credits_and_debits():
    fields = extract_fields(BANK_STATEMENT_TEXT, AnalyzedDocumentType.BANK_STATEMENT)
    results = RulesEngine().run(AnalyzedDocumentType.BANK_STATEMENT, fields)
    reconciliation = next(
        r for r in results if r["rule_id"] == "CLOSING_MATCHES_TRANSACTIONS"
    )
    assert reconciliation["status"] == "pass"


def test_rule_reconciliation_fails_on_mismatch():
    fields = extract_fields(BANK_STATEMENT_TEXT, AnalyzedDocumentType.BANK_STATEMENT)
    fields["closing_balance"] = 9999.99
    results = RulesEngine().run(AnalyzedDocumentType.BANK_STATEMENT, fields)
    reconciliation = next(
        r for r in results if r["rule_id"] == "CLOSING_MATCHES_TRANSACTIONS"
    )
    assert reconciliation["status"] == "fail"


def test_rule_zero_transactions_keeps_balance():
    text = BANK_STATEMENT_TEXT.replace("Transactions: 23", "Transactions: 0")
    text = text.replace("Total Credits: 2,500.00", "Total Credits: -")
    text = text.replace("Total Debits: 549.75", "Total Debits: -")
    fields = extract_fields(text, AnalyzedDocumentType.BANK_STATEMENT)
    fields["closing_balance"] = fields["opening_balance"]
    results = RulesEngine().run(AnalyzedDocumentType.BANK_STATEMENT, fields)
    reconciliation = next(
        r for r in results if r["rule_id"] == "CLOSING_MATCHES_TRANSACTIONS"
    )
    assert reconciliation["status"] == "pass"


def test_rule_net_le_gross_fails():
    fields = extract_fields(PAYSLIP_TEXT, AnalyzedDocumentType.PAYSLIP)
    fields["net_salary"] = 99999.0
    results = RulesEngine().run(AnalyzedDocumentType.PAYSLIP, fields)
    assert next(r for r in results if r["rule_id"] == "NET_LE_GROSS")["status"] == "fail"


def test_rule_payment_date_outside_month_fails():
    fields = extract_fields(PAYSLIP_TEXT, AnalyzedDocumentType.PAYSLIP)
    fields["payment_date"] = "2026-06-15"
    results = RulesEngine().run(AnalyzedDocumentType.PAYSLIP, fields)
    rule = next(r for r in results if r["rule_id"] == "PAYMENT_WITHIN_MONTH")
    assert rule["status"] == "fail"


def test_rule_expiry_before_issue_fails():
    fields = extract_fields(ID_TEXT, AnalyzedDocumentType.ID_DOCUMENT)
    fields["issue_date"] = "2030-01-01"
    results = RulesEngine().run(AnalyzedDocumentType.ID_DOCUMENT, fields)
    rule = next(r for r in results if r["rule_id"] == "EXPIRY_AFTER_ISSUE")
    assert rule["status"] == "fail"


def test_rule_age_reasonable():
    fields = extract_fields(ID_TEXT, AnalyzedDocumentType.ID_DOCUMENT)
    results = RulesEngine().run(AnalyzedDocumentType.ID_DOCUMENT, fields)
    assert next(r for r in results if r["rule_id"] == "AGE_REASONABLE")["status"] == "pass"


# --- Scoring -----------------------------------------------------------------


def test_compute_score_is_weighted():
    score = compute_score(field_coverage=1.0, validation_rate=1.0, consistency_rate=1.0)
    assert score == 1.0
    score = compute_score(field_coverage=0.5, validation_rate=0.5, consistency_rate=0.5)
    assert score == 0.5
    score = compute_score(field_coverage=0.0, validation_rate=1.0, consistency_rate=1.0)
    assert score == 0.5


def test_compute_score_clamps():
    assert compute_score(field_coverage=2.0, validation_rate=2.0, consistency_rate=2.0) == 1.0
    assert compute_score(field_coverage=-1.0, validation_rate=0.0, consistency_rate=0.0) == 0.0


def test_status_derivation_branches():
    assert compute_verification_status(0.9, missing_critical_fields=False,
                                      critical_validation_failures=False,
                                      consistency_failures=False) is VerificationStatus.VERIFIED
    assert compute_verification_status(0.7, missing_critical_fields=False,
                                      critical_validation_failures=False,
                                      consistency_failures=False) is VerificationStatus.PARTIALLY_VERIFIED
    assert compute_verification_status(0.5, missing_critical_fields=False,
                                      critical_validation_failures=False,
                                      consistency_failures=False) is VerificationStatus.NEEDS_REVIEW
    assert compute_verification_status(0.2, missing_critical_fields=False,
                                      critical_validation_failures=False,
                                      consistency_failures=False) is VerificationStatus.FAILED


def test_status_forced_to_needs_review():
    assert compute_verification_status(0.95, missing_critical_fields=True,
                                      critical_validation_failures=False,
                                      consistency_failures=False) is VerificationStatus.NEEDS_REVIEW
    assert compute_verification_status(0.95, missing_critical_fields=False,
                                      critical_validation_failures=True,
                                      consistency_failures=False) is VerificationStatus.NEEDS_REVIEW
    assert compute_verification_status(0.95, missing_critical_fields=False,
                                      critical_validation_failures=False,
                                      consistency_failures=True) is VerificationStatus.NEEDS_REVIEW


def test_scoring_components_full_statement_verifies():
    document_type, fields, validations, consistency = _components(BANK_STATEMENT_TEXT)
    coverage, v_rate, c_rate, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    assert coverage == 1.0
    assert v_rate == 1.0
    assert c_rate == 1.0
    assert score == 1.0
    assert status is VerificationStatus.VERIFIED


def test_scoring_components_missing_critical_field():
    text = BANK_STATEMENT_TEXT.replace("Opening Balance: 1,250.50", "Opening Balance: -")
    document_type, fields, validations, consistency = _components(text)
    _, _, _, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    assert score < 1.0
    assert status is VerificationStatus.NEEDS_REVIEW


def test_issues_are_human_readable():
    text = BANK_STATEMENT_TEXT.replace("Opening Balance: 1,250.50", "Opening Balance: -")
    document_type, _, validations, consistency = _components(text)
    issues = [
        v["message"] for v in validations if v["status"] != "valid"
    ] + [c["message"] for c in consistency if c["status"] != "pass"]
    assert any("Opening balance missing" in message for message in issues)


# --- Repository --------------------------------------------------------------


def _seed_application_and_document() -> tuple[int, int]:
    db = SessionLocal()
    try:
        application = ApplicationRepository(db).create(created_by="repo-test")
        document = DocumentRepository(db).create(
            application_id=application.id,
            document_type=DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
            original_filename="statement.pdf",
            stored_file_path="applications/APP-test/statement.pdf",
            file_type="application/pdf",
        )
        return application.id, document.id
    finally:
        db.close()


def test_repository_upsert_creates_then_updates():
    application_id, document_id = _seed_application_and_document()
    db = SessionLocal()
    try:
        repository = DocumentAnalysisRepository(db)
        first = repository.upsert(
            application_id=application_id,
            document_id=document_id,
            document_type=AnalyzedDocumentType.BANK_STATEMENT.value,
            extracted_fields={"account_number": "123"},
            validation_results=[{"field": "account_number", "status": "valid"}],
            consistency_results=[],
            confidence_score=0.7,
            verification_status=VerificationStatus.PARTIALLY_VERIFIED.value,
            analysis_version="1.0.0",
            processing_time_ms=10,
        )
        assert repository.get_by_document(document_id) is first
        updated = repository.upsert(
            application_id=application_id,
            document_id=document_id,
            document_type=AnalyzedDocumentType.BANK_STATEMENT.value,
            extracted_fields={"account_number": "456", "iban": "DE..."},
            validation_results=[{"field": "account_number", "status": "valid"}],
            consistency_results=[],
            confidence_score=0.9,
            verification_status=VerificationStatus.VERIFIED.value,
            analysis_version="1.0.0",
            processing_time_ms=20,
        )
        assert updated.id == first.id
        results = repository.get_by_application(application_id)
        assert len(results) == 1
        assert results[0].extracted_fields == {"account_number": "456", "iban": "DE..."}
        assert results[0].confidence_score == 0.9
        assert results[0].verification_status == VerificationStatus.VERIFIED.value
    finally:
        db.close()
