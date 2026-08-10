import pytest
from app.rules.rule_engine import RuleEngine
from app.schemas.document_schemas import (
    ExtractedDocument, 
    DocumentType, 
    TripartiteData, 
    BilateralData,
    AccountMaintenanceData,
    BankDetails,
    SignatureInfo,
    StampInfo
)
from app.schemas.verification_schemas import VerificationStatus


@pytest.fixture
def engine():
    return RuleEngine()


@pytest.fixture
def good_tripartite():
    return ExtractedDocument(
        document_type=DocumentType.TRIPARTITE,
        file_name="tripartite.pdf",
        tripartite=TripartiteData(
            has_preamble_date=False,
            bank_details=BankDetails(account_number="12345", iban="PK12ABCD1234567890123456"),
            signatures=[SignatureInfo(is_present=True)],
            stamp=StampInfo(is_present=True)
        )
    )


@pytest.fixture
def bad_tripartite():
    return ExtractedDocument(
        document_type=DocumentType.TRIPARTITE,
        file_name="bad_tri.pdf",
        tripartite=TripartiteData(
            has_preamble_date=True,  # Should fail rule
            date_in_preamble="01-01-2026",
            bank_details=BankDetails(account_number="12345", iban="PK12ABCD1234567890123456"),
            signatures=[SignatureInfo(is_present=False)], # Missing signature
            stamp=StampInfo(is_present=False) # Missing stamp
        )
    )


@pytest.fixture
def good_bilateral():
    return ExtractedDocument(
        document_type=DocumentType.BILATERAL,
        file_name="bilateral.pdf",
        bilateral=BilateralData(
            platform_mentioned="Digital Muhasil",
            section_6_account=BankDetails(account_number="12345", iban="PK12ABCD1234567890123456"),
            party_a_signed=True,
            stamp=StampInfo(is_present=True)
        )
    )


def test_verify_document_pass(engine, good_tripartite):
    result = engine.verify_document(good_tripartite)
    
    assert result.document_type == "tripartite_agreement"
    assert result.overall_status == VerificationStatus.PASS
    assert result.pass_count == 3  # signature, stamp, blank date rules
    assert result.fail_count == 0


def test_verify_document_fail(engine, bad_tripartite):
    result = engine.verify_document(bad_tripartite)
    
    assert result.overall_status == VerificationStatus.FAIL
    assert result.fail_count == 3  # signature missing, stamp missing, date not blank
    
    # Check specific rule failure message
    date_rule_result = next(r for r in result.rule_results if r.rule_id == "TRI_001_BLANK_DATE")
    assert date_rule_result.status == VerificationStatus.FAIL
    assert date_rule_result.field_value == "01-01-2026"


def test_cross_document_matching_pass(engine, good_tripartite, good_bilateral):
    documents = [good_tripartite, good_bilateral]
    cross_checks = engine.perform_cross_document_checks(documents)
    
    assert len(cross_checks) == 2  # account_number, iban
    for check in cross_checks:
        assert check.is_consistent is True
        assert check.status == VerificationStatus.PASS


def test_cross_document_matching_fail(engine, good_tripartite):
    # Create a mismatched bilateral
    bad_bilateral = ExtractedDocument(
        document_type=DocumentType.BILATERAL,
        file_name="bad_bilateral.pdf",
        bilateral=BilateralData(
            platform_mentioned="Digital Muhasil",
            section_6_account=BankDetails(account_number="99999", iban="PK99WRONG") # Mismatch
        )
    )
    
    documents = [good_tripartite, bad_bilateral]
    cross_checks = engine.perform_cross_document_checks(documents)
    
    assert len(cross_checks) == 2  # account_number, iban
    for check in cross_checks:
        assert check.is_consistent is False
        assert check.status == VerificationStatus.FAIL


def test_generate_verification_report(engine, good_tripartite, good_bilateral):
    docs = [good_tripartite, good_bilateral]
    report = engine.generate_verification_report("CASE-001", docs)
    
    assert report.case_id == "CASE-001"
    assert report.overall_status == VerificationStatus.PASS
    assert len(report.document_results) == 2
    assert len(report.cross_document_checks) == 2
    assert report.total_fail == 0
