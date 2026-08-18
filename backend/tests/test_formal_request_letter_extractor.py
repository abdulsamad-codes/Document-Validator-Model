"""Unit tests for FormalRequestLetterExtractor using synthetic fixtures.

Validates document type detection, pattern field extraction, validation,
and confidence scoring for formal request letters.
"""

from app.document_analysis.constants import (
    AnalyzedDocumentType,
    VerificationStatus,
)
from app.document_analysis.extractors import (
    FormalRequestLetterExtractor,
    detect_document_type,
    extract_fields,
)
from app.document_analysis.rules import RulesEngine
from app.document_analysis.validators import ValidatorEngine

SYNTHETIC_FORMAL_REQUEST_LETTER = """
OFFICE OF THE ASSISTANT DIRECTOR
LOCAL GOVERNMENT & RURAL DEVELOPMENT DEPARTMENT
DISTRICT DIR UPPER

No. AD/LGRDD/DU/2026/1045
Dated: 15/05/2026

To,
The Managing Director,
Khyber Pakhtunkhwa Information Technology Board (KPITB),
Peshawar.

Subject: Request for Onboarding as a Sub-Biller with KPITB Digital Payment Gateway

Respected Sir,

It is submitted that this department intends to digitize its fee collection mechanisms across the district. We request KPITB to kindly onboard our department as a sub-biller on the Digital Muhasil / PayMin platform.

Focal Person Name: Mohammad Ali Khan
Designation: Assistant Director

Yours faithfully,

(Authorized Signatory)
Assistant Director
Local Government & Rural Development Department
"""


def test_detect_formal_request_letter():
    """Detect formal request letter type from keyword scoring."""
    doc_type = detect_document_type(SYNTHETIC_FORMAL_REQUEST_LETTER)
    assert doc_type is AnalyzedDocumentType.FORMAL_REQUEST_LETTER


def test_formal_request_letter_extraction():
    """Extract fields from synthetic formal request letter text."""
    fields = extract_fields(
        SYNTHETIC_FORMAL_REQUEST_LETTER, AnalyzedDocumentType.FORMAL_REQUEST_LETTER
    )
    assert fields.get("addressee") is not None
    assert "Managing Director" in fields["addressee"]
    assert fields.get("subject") is not None
    assert "Onboarding as a Sub-Biller" in fields["subject"]
    assert fields.get("date") == "2026-05-15"
    assert fields.get("focal_person_name") == "Mohammad Ali Khan"
    assert fields.get("focal_person_designation") == "Assistant Director"


def test_formal_request_letter_validation_and_rules():
    """Validate extracted fields and run rules for formal request letter."""
    fields = extract_fields(
        SYNTHETIC_FORMAL_REQUEST_LETTER, AnalyzedDocumentType.FORMAL_REQUEST_LETTER
    )
    validations = ValidatorEngine().run(
        AnalyzedDocumentType.FORMAL_REQUEST_LETTER, fields
    )
    rules = RulesEngine().run(
        AnalyzedDocumentType.FORMAL_REQUEST_LETTER, fields
    )

    # Check date validator passed
    date_val = next((v for v in validations if v["field"] == "date"), None)
    assert date_val is not None
    assert date_val["status"] == "valid"
