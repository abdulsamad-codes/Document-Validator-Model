"""
Pydantic schemas for verification results and API responses.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum


class VerificationStatus(str, Enum):
    """Possible outcomes of a single rule check."""
    PASS = "PASS"
    WARNING = "WARNING"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    FAIL = "FAIL"
    REJECTED = "REJECTED"


class RuleCheckResult(BaseModel):
    """Result of evaluating a single business rule."""
    rule_id: str = Field(..., description="Unique identifier for the rule (e.g., 'AUTH_LETTERHEAD')")
    rule_name: str = Field(..., description="Human-readable rule name")
    document_type: str = Field(..., description="Document this rule applies to")
    status: VerificationStatus
    message: str = Field(..., description="Explanation of the result")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="OCR/detection confidence")
    field_value: Optional[str] = Field(None, description="The extracted value that was checked")
    expected_value: Optional[str] = Field(None, description="What was expected (for mismatches)")


class CrossDocumentMatch(BaseModel):
    """Result of cross-document field comparison."""
    field_name: str = Field(..., description="Field being compared (e.g., 'account_number')")
    documents_compared: List[str] = Field(..., description="Document types that were compared")
    values_found: Dict[str, Optional[str]] = Field(..., description="Value found in each document")
    is_consistent: bool = Field(..., description="Whether all values match")
    status: VerificationStatus
    message: str


class DocumentVerificationResult(BaseModel):
    """Complete verification result for a single document."""
    document_type: str
    file_name: str
    rule_results: List[RuleCheckResult] = Field(default_factory=list)
    pass_count: int = 0
    fail_count: int = 0
    warning_count: int = 0
    manual_review_count: int = 0
    overall_status: VerificationStatus = VerificationStatus.PASS


class VerificationReport(BaseModel):
    """
    Complete verification report for an entire sub-biller onboarding package.
    This is the final output of the verification pipeline.
    """
    case_id: str = Field(..., description="Unique case/application identifier")
    organization_name: Optional[str] = None
    submitted_at: datetime = Field(default_factory=datetime.now)
    verified_at: Optional[datetime] = None

    # Per-document results
    document_results: List[DocumentVerificationResult] = Field(default_factory=list)

    # Cross-document consistency checks
    cross_document_checks: List[CrossDocumentMatch] = Field(default_factory=list)

    # Aggregate summary
    total_rules_checked: int = 0
    total_pass: int = 0
    total_fail: int = 0
    total_warnings: int = 0
    total_manual_review: int = 0

    # Final verdict
    overall_status: VerificationStatus = VerificationStatus.PASS
    reviewer_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
