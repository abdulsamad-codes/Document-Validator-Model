"""
Pydantic schemas defining the structured data extracted from each document type.

These schemas are the contract between the OCR/Field Extraction layer
and the Rule Engine / Cross-Document Matcher.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================
class DocumentType(str, Enum):
    """Types of documents in a sub-biller onboarding package."""
    AUTHORITY_LETTER = "authority_letter"
    ACCOUNT_MAINTENANCE = "account_maintenance_certificate"
    APPLICATION_FORM = "application_form"
    DECLARATION = "declaration_of_sub_biller"
    TRIPARTITE = "tripartite_agreement"
    BILATERAL = "bilateral_agreement"
    ESTAMP = "e_stamp_paper"
    SCHEDULE_OF_CHARGES = "schedule_of_charges"
    BRD = "business_requirement_document"
    REQUEST_LETTER = "formal_request_letter"
    CNIC = "cnic_copy"


# ============================================================================
# SHARED FIELD MODELS
# ============================================================================
class BankDetails(BaseModel):
    """Bank account information extracted from a document."""
    account_title: Optional[str] = Field(None, description="Title of the bank account")
    account_number: Optional[str] = Field(None, description="Bank account number")
    iban: Optional[str] = Field(None, description="IBAN (if present)")
    branch_name: Optional[str] = Field(None, description="Bank branch name")
    branch_code: Optional[str] = Field(None, description="Bank branch code/number")


class PersonInfo(BaseModel):
    """Information about an individual (focal person, director, proprietor)."""
    name: Optional[str] = Field(None, description="Full name")
    designation: Optional[str] = Field(None, description="Designation/title")
    cnic_number: Optional[str] = Field(None, description="CNIC number (xxxxx-xxxxxxx-x)")


class StampInfo(BaseModel):
    """Detected stamp/seal information."""
    is_present: bool = Field(False, description="Whether a stamp/seal was detected")
    is_readable: bool = Field(False, description="Whether stamp text is readable")
    bounding_box: Optional[List[int]] = Field(None, description="[x, y, w, h] of detected stamp")


class SignatureInfo(BaseModel):
    """Detected signature information."""
    is_present: bool = Field(False, description="Whether a signature was detected")
    bounding_box: Optional[List[int]] = Field(None, description="[x, y, w, h] of detected signature")
    page_number: Optional[int] = Field(None, description="Page where signature was found")


# ============================================================================
# DOCUMENT-SPECIFIC SCHEMAS
# ============================================================================
class AuthorityLetterData(BaseModel):
    """Extracted fields from the Authority Letter."""
    has_letterhead: Optional[bool] = Field(None, description="Printed on official department letterhead")
    focal_person: Optional[PersonInfo] = None
    account_maintenance_at_top: Optional[bool] = Field(None, description="Account maintenance info at top")
    stamp: Optional[StampInfo] = None
    signature: Optional[SignatureInfo] = None
    raw_text: Optional[str] = None


class AccountMaintenanceData(BaseModel):
    """Extracted fields from the Account Maintenance Certificate."""
    has_bank_letterhead: Optional[bool] = Field(None, description="Issued on bank letterhead")
    bank_details: Optional[BankDetails] = None
    stamp: Optional[StampInfo] = None
    signature: Optional[SignatureInfo] = None
    raw_text: Optional[str] = None


class ApplicationFormData(BaseModel):
    """Extracted fields from the 1-Link Application Form."""
    organization_name: Optional[str] = None
    ntn: Optional[str] = Field(None, description="NTN or 'N/A'")
    country_of_incorporation: Optional[str] = None
    bank_details: Optional[BankDetails] = None
    nature_of_business: Optional[str] = None
    organization_type: Optional[str] = None
    business_classification: Optional[str] = None
    license_details: Optional[str] = None
    proprietors: Optional[List[PersonInfo]] = Field(default_factory=list)
    all_pages_signed: Optional[bool] = Field(None, description="Every page signed and stamped")
    declaration_signed: Optional[bool] = Field(None, description="Declaration of Sub-Member signed")
    aggregator_section_signed: Optional[bool] = Field(None, description="KPITB Aggregator section signed")
    stamp: Optional[StampInfo] = None
    raw_text: Optional[str] = None


class TripartiteData(BaseModel):
    """Extracted fields from the Tripartite Agreement."""
    parties: Optional[List[str]] = Field(default_factory=list, description="Named parties")
    organization_name: Optional[str] = None
    bank_details: Optional[BankDetails] = None
    date_in_preamble: Optional[str] = Field(None, description="Date in first 2 lines (should be blank)")
    has_preamble_date: Optional[bool] = Field(None, description="True if date found in preamble")
    numbering_correct: Optional[bool] = Field(None, description="Point numbering is sequential")
    signatures: Optional[List[SignatureInfo]] = Field(default_factory=list)
    witnesses: Optional[List[PersonInfo]] = Field(default_factory=list)
    stamp: Optional[StampInfo] = None
    raw_text: Optional[str] = None


class BilateralData(BaseModel):
    """Extracted fields from the Bilateral Agreement (SLA)."""
    organization_name: Optional[str] = None
    platform_mentioned: Optional[str] = Field(None, description="PayMin / Digital Muhasil / Paymere BCX")
    text_intact: Optional[bool] = Field(None, description="Main body text matches template")
    dates_blank: Optional[bool] = Field(None, description="Required dates left blank")
    section_5_2_charges: Optional[str] = Field(None, description="Section 5.2 transaction charges text")
    charges_in_pkr: Optional[bool] = Field(None, description="Charges stated in PKR")
    section_6_account: Optional[BankDetails] = None
    party_a_signed: Optional[bool] = None
    party_b_signed: Optional[bool] = None
    party_a_witnesses: Optional[List[PersonInfo]] = Field(default_factory=list)
    party_b_witnesses: Optional[List[PersonInfo]] = Field(default_factory=list)
    stamp: Optional[StampInfo] = None
    raw_text: Optional[str] = None


class EStampData(BaseModel):
    """Extracted fields from E-Stamp Papers."""
    has_brownish_texture: Optional[bool] = Field(None, description="Resembles real e-stamp appearance")
    non_judicial_description: Optional[str] = None
    first_party: Optional[str] = None
    second_party: Optional[str] = None
    watermark_valid: Optional[bool] = None
    notary_stamp_present: Optional[bool] = None
    raw_text: Optional[str] = None


class BRDData(BaseModel):
    """Extracted fields from the Business Requirement Document."""
    services_listed: Optional[List[str]] = Field(default_factory=list, description="Revenue services to digitize")
    has_required_services: Optional[bool] = None
    stamp: Optional[StampInfo] = None
    signature: Optional[SignatureInfo] = None
    raw_text: Optional[str] = None


class RequestLetterData(BaseModel):
    """Extracted fields from the Formal Request Letter."""
    subject_line: Optional[str] = None
    mentions_sub_biller: Optional[bool] = Field(None, description="Mentions 'sub-biller' onboarding")
    mentions_kpitb: Optional[bool] = Field(None, description="Mentions KPITB")
    stamp: Optional[StampInfo] = None
    signature: Optional[SignatureInfo] = None
    raw_text: Optional[str] = None


class CNICData(BaseModel):
    """Extracted fields from CNIC copies."""
    cnic_number: Optional[str] = None
    holder_name: Optional[str] = None
    is_readable: Optional[bool] = None
    is_expired: Optional[bool] = None
    raw_text: Optional[str] = None


# ============================================================================
# UNIFIED DOCUMENT RECORD
# ============================================================================
class ExtractedDocument(BaseModel):
    """
    Unified wrapper for any document type with its extracted structured data.
    """
    document_type: DocumentType
    file_name: str
    page_count: Optional[int] = None
    ocr_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)

    # Only one of these will be populated depending on document_type
    authority_letter: Optional[AuthorityLetterData] = None
    account_maintenance: Optional[AccountMaintenanceData] = None
    application_form: Optional[ApplicationFormData] = None
    tripartite: Optional[TripartiteData] = None
    bilateral: Optional[BilateralData] = None
    estamp: Optional[EStampData] = None
    brd: Optional[BRDData] = None
    request_letter: Optional[RequestLetterData] = None
    cnic: Optional[CNICData] = None
