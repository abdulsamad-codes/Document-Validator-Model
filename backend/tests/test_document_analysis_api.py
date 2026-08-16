"""Tests for the document analysis API and end-to-end analysis flow.

End-to-end tests exercise the full chain through the real API: upload a
document, run Phase 5 technical validation, run Phase 6 document processing and
finally Phase 7 analysis. Digital PDFs carry their analysis text directly
(PyMuPDF probe); scanned images use the deterministic fake OCR engine so no
PaddleOCR model is required.
"""

import pymupdf
import pytest

from app.database.connection import SessionLocal
from app.database.models.document_analysis_result import DocumentAnalysisResult
from app.database.models.enums import DocumentType
from tests.test_document_processing_api import patch_ocr_engine, process_documents
from tests.test_technical_validation_api import (
    add_document,
    create_application,
    encode_png,
    make_document_image,
    run_validation,
)

API = "/api/v1"

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

PLAIN_TEXT = (
    "Dear Sir or Madam, please find attached the meeting minutes from our "
    "quarterly board session for your records. Kind regards."
)

#: Synthetic (fabricated, non-real) fixture mirroring docs/Master_Rules_Combined.md
#: Section 7's structure for a Bilateral Agreement. Never real extracted values.
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

#: Synthetic (fabricated, non-real) fixtures mirroring the checklist types.
#: Never real extracted values.
ACCOUNT_MAINTENANCE_CERTIFICATE_TEXT = """FUTURE BANK LIMITED
ACCOUNT MAINTENANCE CERTIFICATE

This is to certify that the following account is maintained with us:

Account Title: KHYBER PROVINCE UTILITIES BOARD
Account Number: 01234567890123
IBAN: PK36FUTB0000001123456702
Bank Name: Future Bank Limited
Branch Name: Main Branch, Peshawar
Date of Issue: 15/08/2026
"""

TRIPARTITE_AGREEMENT_TEXT = """TRIPARTITE AGREEMENT
This Tripartite Agreement is made and entered into by and between:
1-Link (Private) Limited, having its registered office at 4th Floor, State Life Building, Karachi (hereinafter referred to as '1-Link')
Khyber Pakhtunkhwa Information Technology Board, having its registered office at Civil Secretariat, Peshawar (hereinafter referred to as 'KPITB')
Transport and Mass Transit Department, Government of Khyber Pakhtunkhwa, having its office at Peshawar (hereinafter referred to as the 'Sub-biller')

Bank Details:
Account Title: KHYBER PROVINCE UTILITIES BOARD
Account Number: 01234567890123
Branch: Main Branch, Peshawar
"""

#: Synthetic (fabricated, non-real) fixture mirroring the real prose-embedded
#: Authority Letter template confirmed on two independent real departments in
#: Confidential Data/. Never real extracted values. Deliberately mentions
#: "Account" nowhere, matching real evidence that Authority Letters routinely
#: omit bank details -- this is also what proves the routing-precedence fix:
#: this text has zero bank-statement-shaped labels for detect_document_type's
#: keyword table to latch onto.
AUTHORITY_LETTER_TEXT = """AUTHORITY LETTER
It is hereby authorized that Mr. Naveed Khan, Deputy Director Administration
(BPS-18) is authorized to deal with and conduct correspondence and matter related
to 1-Link and the Khyber Pakhtunkhwa Information Technology Board (KPITB) on the
behalf of Directorate.
"""


def make_text_pdf_bytes(text: str) -> bytes:
    """Build a digital PDF whose probed text is exactly ``text``."""
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    y = 72
    for line in text.splitlines():
        if not line.strip():
            continue
        page.insert_text((72, y), line, fontsize=12)
        y += 18
    content = document.tobytes()
    document.close()
    return content


def add_digital_pdf(
    storage_root,
    application_id: int,
    text: str,
    *,
    document_type: DocumentType = DocumentType.OTHER_SUPPORTING_DOCUMENT,
    filename: str = "statement.pdf",
) -> int:
    """Upload a digital PDF carrying ``text`` and return its document id.

    Defaults to ``OTHER_SUPPORTING_DOCUMENT`` -- the storage type on which
    ``detect_document_type``'s OCR keyword table is the correct classifier
    (bank statement, payslip, etc.). A checklist storage type (e.g.
    ``ACCOUNT_MAINTENANCE_CERTIFICATE``) would instead be routed to that
    type's own real extractor, bypassing keyword detection entirely.
    """
    return add_document(
        storage_root,
        application_id,
        document_type,
        filename,
        make_text_pdf_bytes(text),
        "application/pdf",
    )


def analyze_documents(client, application_id: int) -> dict:
    """Call the analyze-documents endpoint and return the JSON response."""
    response = client.post(f"{API}/applications/{application_id}/analyze-documents")
    assert response.status_code == 200, response.text
    return response.json()


def get_analysis_results(client, application_id: int) -> dict:
    """Call the analysis-results endpoint and return the JSON response."""
    response = client.get(f"{API}/applications/{application_id}/analysis-results")
    assert response.status_code == 200, response.text
    return response.json()


def stored_analysis_count() -> int:
    """Return the number of persisted analysis result rows."""
    db = SessionLocal()
    try:
        return len(db.query(DocumentAnalysisResult).all())
    finally:
        db.close()


def run_processing(client, application_id: int) -> dict:
    """Validate then process an application so its OCR results exist."""
    run_validation(client, application_id)
    return process_documents(client, application_id)


# --- End-to-end analysis -----------------------------------------------------


def test_analyze_bank_statement_end_to_end(authenticated_client, storage_root, monkeypatch):
    application_id = create_application(authenticated_client)
    add_digital_pdf(
        storage_root,
        application_id,
        BANK_STATEMENT_TEXT,
        document_type=DocumentType.OTHER_SUPPORTING_DOCUMENT,
    )
    run_processing(authenticated_client, application_id)
    engine = patch_ocr_engine(monkeypatch)

    result = analyze_documents(authenticated_client, application_id)

    assert result["total_analyzed"] == 1
    assert result["total_failed"] == 0
    item = result["items"][0]
    assert item["outcome"] == "ANALYZED"
    assert item["document_type"] == "BANK_STATEMENT"
    assert item["verification_status"] == "VERIFIED"
    assert item["confidence_score"] == 1.0
    assert item["extracted_fields"]["account_number"] == "1234567890"
    assert item["extracted_fields"]["opening_balance"] == 1250.5
    assert item["issues"] == []
    assert engine.calls == 0
    assert stored_analysis_count() == 1

    stored = get_analysis_results(authenticated_client, application_id)
    assert stored["total"] == 1
    item = stored["items"][0]
    assert item["verification_status"] == "VERIFIED"
    assert item["confidence_score"] == 1.0
    assert item["extracted_fields"]["iban"] == "DE89370400440532013000"
    assert item["issues"] == []
    assert item["created_at"] is not None


def test_analyze_payslip_from_scanned_image(authenticated_client, storage_root, monkeypatch):
    application_id = create_application(authenticated_client)
    add_document(
        storage_root,
        application_id,
        DocumentType.ONE_LINK_LETTER,
        "payslip.png",
        encode_png(make_document_image()),
        "image/png",
    )
    run_validation(authenticated_client, application_id)
    engine = patch_ocr_engine(monkeypatch, texts=[PAYSLIP_TEXT])
    process_documents(authenticated_client, application_id)

    result = analyze_documents(authenticated_client, application_id)

    assert result["total_analyzed"] == 1
    item = result["items"][0]
    assert item["document_type"] == "PAYSLIP"
    assert item["verification_status"] == "VERIFIED"
    assert item["extracted_fields"]["employee_name"] == "Jane Q. Roe"
    assert item["extracted_fields"]["gross_salary"] == 5000.0
    assert item["extracted_fields"]["net_salary"] == 3850.5
    assert engine.calls == 1


def test_analyze_identity_document(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_digital_pdf(
        storage_root,
        application_id,
        ID_TEXT,
        document_type=DocumentType.OTHER_SUPPORTING_DOCUMENT,
        filename="id.pdf",
    )
    run_processing(authenticated_client, application_id)

    result = analyze_documents(authenticated_client, application_id)

    item = result["items"][0]
    assert item["document_type"] == "ID_DOCUMENT"
    assert item["verification_status"] == "VERIFIED"
    assert item["extracted_fields"]["full_name"] == "Jose P. Garcia"
    assert item["extracted_fields"]["expiry_date"] == "2028-06-01"


def test_analyze_tax_document(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_digital_pdf(
        storage_root,
        application_id,
        TAX_TEXT,
        document_type=DocumentType.SCHEDULE_OF_CHARGES,
        filename="tax.pdf",
    )
    run_processing(authenticated_client, application_id)

    result = analyze_documents(authenticated_client, application_id)

    item = result["items"][0]
    assert item["document_type"] == "TAX_DOCUMENT"
    assert item["verification_status"] == "VERIFIED"
    assert item["extracted_fields"]["tax_reference_number"] == "TAX-2025-000123"
    assert item["extracted_fields"]["total_tax"] == 9800.0


# --- Failure handling --------------------------------------------------------


def test_analyze_without_ocr_result_fails_document(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_digital_pdf(storage_root, application_id, BANK_STATEMENT_TEXT)
    run_validation(authenticated_client, application_id)

    result = analyze_documents(authenticated_client, application_id)

    assert result["total_analyzed"] == 0
    assert result["total_failed"] == 1
    item = result["items"][0]
    assert item["outcome"] == "FAILED"
    assert "No OCR result found" in item["message"]
    assert stored_analysis_count() == 0


def test_analyze_unknown_document_type_persists_needs_review(authenticated_client, storage_root):
    """A document outside the 4-category keyword table must stay visible.

    Previously this raised ``UnsupportedDocumentType``, which was caught and
    turned into an in-memory-only failed item -- no ``DocumentAnalysisResult``
    row was ever persisted, so the document silently vanished from
    ``document_analysis_results`` and everything downstream (confidence
    scoring, reports) had no record it existed. It must now be analysed (not
    failed) with a NEEDS_REVIEW status and a real stored row, so a human
    reviewer sees it rather than the pipeline quietly dropping it.
    """
    application_id = create_application(authenticated_client)
    add_digital_pdf(
        storage_root,
        application_id,
        PLAIN_TEXT,
        document_type=DocumentType.OTHER_SUPPORTING_DOCUMENT,
        filename="letter.pdf",
    )
    run_processing(authenticated_client, application_id)

    result = analyze_documents(authenticated_client, application_id)

    assert result["total_analyzed"] == 1
    assert result["total_failed"] == 0
    item = result["items"][0]
    assert item["outcome"] == "ANALYZED"
    assert item["document_type"] == "UNKNOWN"
    assert item["verification_status"] == "NEEDS_REVIEW"
    assert item["extracted_fields"] == {}
    assert item["confidence_score"] is None
    assert "could not be determined" in item["message"]
    assert stored_analysis_count() == 1

    # The row must be independently readable, not just present in the
    # immediate response -- this is what "silently excluded" actually meant.
    stored = get_analysis_results(authenticated_client, application_id)
    assert stored["total"] == 1
    stored_item = stored["items"][0]
    assert stored_item["document_type"] == "UNKNOWN"
    assert stored_item["verification_status"] == "NEEDS_REVIEW"


def test_analyze_recognized_checklist_type_stores_real_type_not_unknown(
    authenticated_client, storage_root
):
    """A document of a real checklist type is labelled honestly, not UNKNOWN.

    ``detect_document_type`` only recognises 4 categories unrelated to the
    real required-document checklist (Tripartite Agreement, Authority
    Letter, etc.), so it reports UNKNOWN for this text either way. But the
    splitter already classified this document as ONE_LINK_LETTER
    (``document.document_type``), and that's real information -- storing it
    instead of a generic UNKNOWN makes the result distinguishable from a
    document neither classifier could identify at all. No extractor exists
    for this type yet, so fields/confidence must stay empty regardless --
    this is a labelling fix, not new extraction capability.
    """
    application_id = create_application(authenticated_client)
    add_digital_pdf(
        storage_root,
        application_id,
        PLAIN_TEXT,
        document_type=DocumentType.ONE_LINK_LETTER,
        filename="one-link.pdf",
    )
    run_processing(authenticated_client, application_id)

    result = analyze_documents(authenticated_client, application_id)

    assert result["total_analyzed"] == 1
    assert result["total_failed"] == 0
    item = result["items"][0]
    assert item["outcome"] == "ANALYZED"
    assert item["document_type"] == "ONE_LINK_LETTER"
    assert item["verification_status"] == "NEEDS_REVIEW"
    assert item["extracted_fields"] == {}
    assert item["confidence_score"] is None
    assert "recognized as ONE_LINK_LETTER" in item["message"]
    assert "not yet supported" in item["message"]
    assert stored_analysis_count() == 1

    stored = get_analysis_results(authenticated_client, application_id)
    assert stored["total"] == 1
    stored_item = stored["items"][0]
    assert stored_item["document_type"] == "ONE_LINK_LETTER"
    assert stored_item["verification_status"] == "NEEDS_REVIEW"


@pytest.mark.parametrize(
    "document_type",
    [
        DocumentType.BILATERAL_AGREEMENT,
        DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
        DocumentType.ONE_LINK_LETTER,
        DocumentType.AUTHORITY_LETTER,
        DocumentType.SCHEDULE_OF_CHARGES,
        DocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
        DocumentType.FORMAL_REQUEST_LETTER,
        DocumentType.CNIC_FRONT,
        DocumentType.CNIC_BACK,
    ],
)
def test_analyze_every_checklist_type_is_recognized_not_unknown(
    authenticated_client, storage_root, document_type
):
    """Every real checklist category is labelled by its own name, not UNKNOWN."""
    application_id = create_application(authenticated_client)
    add_digital_pdf(
        storage_root,
        application_id,
        PLAIN_TEXT,
        document_type=document_type,
        filename="doc.pdf",
    )
    run_processing(authenticated_client, application_id)

    result = analyze_documents(authenticated_client, application_id)

    item = result["items"][0]
    assert item["outcome"] == "ANALYZED"
    assert item["document_type"] == document_type.value
    assert item["verification_status"] == "NEEDS_REVIEW"
    assert item["extracted_fields"] == {}


def test_analyze_bilateral_agreement_runs_real_extraction(
    authenticated_client, storage_root
):
    """BILATERAL_AGREEMENT now has a real extractor (Phase 1), unlike the
    other 6 checklist types still covered by the "recognized but unsupported"
    stub above. A document typed BILATERAL_AGREEMENT by the splitter must be
    routed to real field extraction, not the stub message.
    """
    application_id = create_application(authenticated_client)
    add_digital_pdf(
        storage_root,
        application_id,
        BILATERAL_AGREEMENT_TEXT,
        document_type=DocumentType.BILATERAL_AGREEMENT,
        filename="bilateral.pdf",
    )
    run_processing(authenticated_client, application_id)

    result = analyze_documents(authenticated_client, application_id)

    assert result["total_analyzed"] == 1
    assert result["total_failed"] == 0
    item = result["items"][0]
    assert item["outcome"] == "ANALYZED"
    assert item["document_type"] == "BILATERAL_AGREEMENT"
    fields = item["extracted_fields"]
    assert fields["organization_name"] == "Sample Regional Development Authority"
    assert fields["platform_name"] == "PayMin"
    assert fields["account_number"] == "9876543210"
    assert fields["iban"] == "DE89370400440532013000"
    assert fields["effective_date"] == "2026-01-15"
    assert item["confidence_score"] is not None
    assert item["confidence_score"] > 0.0
    assert item.get("message") is None

    stored = get_analysis_results(authenticated_client, application_id)
    stored_item = stored["items"][0]
    assert stored_item["document_type"] == "BILATERAL_AGREEMENT"
    assert stored_item["extracted_fields"]["account_number"] == "9876543210"


def test_analyze_account_maintenance_certificate_runs_real_extraction(
    authenticated_client, storage_root
):
    """ACCOUNT_MAINTENANCE_CERTIFICATE has a real extractor. Proves the
    routing-precedence fix: the fixture's own "IBAN"/"Account Number" labels
    score positively against detect_document_type's bank-statement keyword
    table, so without the splitter-first routing this would be mislabelled
    BANK_STATEMENT instead of reaching the AMC extractor.
    """
    application_id = create_application(authenticated_client)
    add_digital_pdf(
        storage_root,
        application_id,
        ACCOUNT_MAINTENANCE_CERTIFICATE_TEXT,
        document_type=DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
        filename="amc.pdf",
    )
    run_processing(authenticated_client, application_id)

    result = analyze_documents(authenticated_client, application_id)

    assert result["total_analyzed"] == 1
    assert result["total_failed"] == 0
    item = result["items"][0]
    assert item["outcome"] == "ANALYZED"
    assert item["document_type"] == "ACCOUNT_MAINTENANCE_CERTIFICATE"
    fields = item["extracted_fields"]
    assert fields["account_holder"] == "KHYBER PROVINCE UTILITIES BOARD"
    assert fields["account_number"] == "01234567890123"
    assert fields["iban"] == "PK36FUTB0000001123456702"
    assert fields["bank_name"] == "Future Bank Limited"
    assert fields["issue_date"] == "2026-08-15"
    assert item["confidence_score"] is not None
    assert item["confidence_score"] > 0.0
    assert item.get("message") is None

    stored = get_analysis_results(authenticated_client, application_id)
    stored_item = stored["items"][0]
    assert stored_item["document_type"] == "ACCOUNT_MAINTENANCE_CERTIFICATE"
    assert stored_item["extracted_fields"]["account_number"] == "01234567890123"


def test_analyze_tripartite_agreement_runs_real_extraction(
    authenticated_client, storage_root
):
    """TRIPARTITE_AGREEMENT has a real extractor (third checklist type)."""
    application_id = create_application(authenticated_client)
    add_digital_pdf(
        storage_root,
        application_id,
        TRIPARTITE_AGREEMENT_TEXT,
        document_type=DocumentType.TRIPARTITE_AGREEMENT,
        filename="tripartite.pdf",
    )
    run_processing(authenticated_client, application_id)

    result = analyze_documents(authenticated_client, application_id)

    assert result["total_analyzed"] == 1
    assert result["total_failed"] == 0
    item = result["items"][0]
    assert item["outcome"] == "ANALYZED"
    assert item["document_type"] == "TRIPARTITE_AGREEMENT"
    fields = item["extracted_fields"]
    assert fields["party_1link"] == "1-Link (Private) Limited"
    assert fields["party_kpitb"] == "Khyber Pakhtunkhwa Information Technology Board"
    assert fields["account_number"] == "01234567890123"
    assert item["confidence_score"] is not None
    assert item["confidence_score"] > 0.0
    assert item.get("message") is None

    stored = get_analysis_results(authenticated_client, application_id)
    stored_item = stored["items"][0]
    assert stored_item["document_type"] == "TRIPARTITE_AGREEMENT"
    assert stored_item["extracted_fields"]["account_number"] == "01234567890123"


def test_analyze_authority_letter_runs_real_extraction(
    authenticated_client, storage_root
):
    """AUTHORITY_LETTER now has a real extractor (Phase 1, second checklist
    type). Also proves the routing-precedence fix: this text has no
    bank-statement-shaped labels at all, so if detect_document_type's
    keyword table ran first (instead of the splitter's own classification),
    it would score 0 and report UNKNOWN rather than reaching this extractor.
    """
    application_id = create_application(authenticated_client)
    add_digital_pdf(
        storage_root,
        application_id,
        AUTHORITY_LETTER_TEXT,
        document_type=DocumentType.AUTHORITY_LETTER,
        filename="authority.pdf",
    )
    run_processing(authenticated_client, application_id)

    result = analyze_documents(authenticated_client, application_id)

    assert result["total_analyzed"] == 1
    assert result["total_failed"] == 0
    item = result["items"][0]
    assert item["outcome"] == "ANALYZED"
    assert item["document_type"] == "AUTHORITY_LETTER"
    fields = item["extracted_fields"]
    assert fields["focal_person_name"] == "Naveed Khan"
    assert fields["focal_person_designation"] == "Deputy Director Administration"
    assert fields["organization_name"] == "Directorate"
    assert item["confidence_score"] is not None
    assert item["confidence_score"] > 0.0
    assert item.get("message") is None

    stored = get_analysis_results(authenticated_client, application_id)
    stored_item = stored["items"][0]
    assert stored_item["document_type"] == "AUTHORITY_LETTER"
    assert stored_item["extracted_fields"]["focal_person_name"] == "Naveed Khan"


def test_analyze_other_supporting_document_still_reports_unknown(
    authenticated_client, storage_root
):
    """OTHER_SUPPORTING_DOCUMENT is the splitter's own catch-all, not a real
    classification -- it must still fall through to UNKNOWN, unchanged."""
    application_id = create_application(authenticated_client)
    add_digital_pdf(
        storage_root,
        application_id,
        PLAIN_TEXT,
        document_type=DocumentType.OTHER_SUPPORTING_DOCUMENT,
        filename="letter.pdf",
    )
    run_processing(authenticated_client, application_id)

    result = analyze_documents(authenticated_client, application_id)

    assert result["items"][0]["document_type"] == "UNKNOWN"


def test_analyze_partial_unknown_type_does_not_block_known_documents(
    authenticated_client, storage_root
):
    """One undetermined document must not affect a known document's analysis."""
    application_id = create_application(authenticated_client)
    add_digital_pdf(
        storage_root,
        application_id,
        BANK_STATEMENT_TEXT,
        document_type=DocumentType.OTHER_SUPPORTING_DOCUMENT,
        filename="statement.pdf",
    )
    add_digital_pdf(
        storage_root,
        application_id,
        PLAIN_TEXT,
        document_type=DocumentType.OTHER_SUPPORTING_DOCUMENT,
        filename="letter.pdf",
    )
    run_processing(authenticated_client, application_id)

    result = analyze_documents(authenticated_client, application_id)

    assert result["total_analyzed"] == 2
    assert result["total_failed"] == 0
    statuses = {item["document_type"]: item["verification_status"] for item in result["items"]}
    assert statuses["BANK_STATEMENT"] == "VERIFIED"
    assert statuses["UNKNOWN"] == "NEEDS_REVIEW"
    assert stored_analysis_count() == 2


def test_analyze_application_not_found(authenticated_client):
    post = authenticated_client.post(f"{API}/applications/999999/analyze-documents")
    assert post.status_code == 404
    get = authenticated_client.get(f"{API}/applications/999999/analysis-results")
    assert get.status_code == 404


def test_get_analysis_results_empty_application(authenticated_client):
    application_id = create_application(authenticated_client)
    result = get_analysis_results(authenticated_client, application_id)
    assert result["total"] == 0
    assert result["items"] == []


def test_reanalysis_upserts_single_row(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_digital_pdf(storage_root, application_id, BANK_STATEMENT_TEXT)
    run_processing(authenticated_client, application_id)

    first = analyze_documents(authenticated_client, application_id)
    second = analyze_documents(authenticated_client, application_id)

    assert first["total_analyzed"] == 1
    assert second["total_analyzed"] == 1
    assert stored_analysis_count() == 1
    assert get_analysis_results(authenticated_client, application_id)["total"] == 1


def test_analyze_partial_failure_isolation(authenticated_client, storage_root, monkeypatch):
    application_id = create_application(authenticated_client)
    add_digital_pdf(storage_root, application_id, BANK_STATEMENT_TEXT)
    add_digital_pdf(
        storage_root,
        application_id,
        PAYSLIP_TEXT,
        document_type=DocumentType.ONE_LINK_LETTER,
        filename="payslip.pdf",
    )
    run_processing(authenticated_client, application_id)

    result = analyze_documents(authenticated_client, application_id)

    assert result["total_analyzed"] == 2
    assert result["total_failed"] == 0


# --- Report content ----------------------------------------------------------


def test_analysis_report_reports_missing_critical_field(authenticated_client, storage_root):
    incomplete = BANK_STATEMENT_TEXT.replace(
        "Opening Balance: 1,250.50", "Opening Balance: -"
    )
    application_id = create_application(authenticated_client)
    add_digital_pdf(
        storage_root,
        application_id,
        incomplete,
        document_type=DocumentType.OTHER_SUPPORTING_DOCUMENT,
    )
    run_processing(authenticated_client, application_id)

    result = analyze_documents(authenticated_client, application_id)

    assert result["total_analyzed"] == 1
    item = result["items"][0]
    assert item["verification_status"] == "NEEDS_REVIEW"
    assert item["confidence_score"] < 1.0
    assert any("Opening balance missing" in issue for issue in item["issues"])
    statuses = {v["field"]: v["status"] for v in item["validation_results"]}
    assert statuses["opening_balance"] == "missing"

    stored = get_analysis_results(authenticated_client, application_id)["items"][0]
    assert stored["verification_status"] == "NEEDS_REVIEW"
    assert any("Opening balance missing" in issue for issue in stored["issues"])
