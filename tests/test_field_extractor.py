import pytest
from app.pipeline.field_extractor import FieldExtractor


@pytest.fixture
def extractor():
    return FieldExtractor()


def test_extract_cnic(extractor):
    # Test perfect CNIC
    assert extractor.extract_cnic("My CNIC is 12345-1234567-1") == "12345-1234567-1"
    
    # Test CNIC without dashes
    assert extractor.extract_cnic("ID: 1234512345671") == "12345-1234567-1"
    
    # Test no CNIC
    assert extractor.extract_cnic("No ID here") is None


def test_extract_iban(extractor):
    # Test perfect IBAN
    assert extractor.extract_iban("Account IBAN: PK12ABCD1234567890123456") == "PK12ABCD1234567890123456"
    
    # Test IBAN with spaces (common in OCR)
    assert extractor.extract_iban("IBAN is PK12 ABCD 1234 5678 9012 3456") == "PK12ABCD1234567890123456"
    
    # Test lowercase
    assert extractor.extract_iban("pk12abcd1234567890123456") == "PK12ABCD1234567890123456"
    
    # Test no IBAN
    assert extractor.extract_iban("Account: 123456789") is None


def test_find_keyword_context(extractor):
    text = "Date of Birth: 01-01-1990. Title of Account: KPITB ONBOARDING. Branch: Main."
    
    context = extractor.find_keyword_context(text, "Title of Account:")
    assert "KPITB ONBOARDING" in context
    
    missing = extractor.find_keyword_context(text, "Nonexistent:")
    assert missing is None


def test_has_keyword(extractor):
    text = "We use Digital Muhasil for payments."
    assert extractor.has_keyword(text, "Digital Muhasil") is True
    assert extractor.has_keyword(text, "PayMin") is False
