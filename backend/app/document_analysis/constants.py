"""Configuration for the document analysis module.

Centralizes the analysed document types, the verification statuses, the scoring
weights and thresholds, and the analysis version. The extractor, validator,
consistency and scoring code consume these constants, so tuning a threshold or
adding a document type never requires touching the service or route layers.
"""

from enum import Enum


class AnalyzedDocumentType(str, Enum):
    """Document categories recognised by the analysis pipeline.

    Independent of the storage-level ``DocumentType`` enum (which only holds the
    upload checklist categories); the analysed category is inferred from the OCR
    text by rule-based heuristics.
    """

    BANK_STATEMENT = "BANK_STATEMENT"
    PAYSLIP = "PAYSLIP"
    ID_DOCUMENT = "ID_DOCUMENT"
    TAX_DOCUMENT = "TAX_DOCUMENT"
    FORMAL_REQUEST_LETTER = "FORMAL_REQUEST_LETTER"
    UNKNOWN = "UNKNOWN"


class VerificationStatus(str, Enum):
    """Overall outcome of the verification scoring."""

    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


#: Version of the extraction/scoring logic. Bumped whenever the rules change so
#: stored results can be traced to the exact logic that produced them.
ANALYSIS_VERSION: str = "1.0.0"

#: Tolerance (in currency units) when reconciling balances.
BALANCE_EPSILON: float = 0.01

#: Deterministic scoring weights. Extraction coverage dominates because a
#: document with missing critical fields cannot be trusted regardless of how
#: clean the remaining validations are.
SCORE_WEIGHT_FIELD_COVERAGE: float = 0.5
SCORE_WEIGHT_VALIDATION: float = 0.3
SCORE_WEIGHT_CONSISTENCY: float = 0.2

#: Score thresholds mapping a confidence score to a verification status.
VERIFIED_MIN_SCORE: float = 0.8
PARTIALLY_VERIFIED_MIN_SCORE: float = 0.6
NEEDS_REVIEW_MIN_SCORE: float = 0.4

# -- Expected and critical field sets per analysed document type --------------
#: Every field a type is expected to carry; used for extraction coverage.
EXPECTED_FIELDS: dict[AnalyzedDocumentType, frozenset[str]] = {
    AnalyzedDocumentType.BANK_STATEMENT: frozenset(
        {
            "account_holder",
            "account_number",
            "iban",
            "bank_name",
            "statement_period",
            "opening_balance",
            "closing_balance",
            "currency",
            "transaction_count",
        }
    ),
    AnalyzedDocumentType.PAYSLIP: frozenset(
        {
            "employee_name",
            "employer_name",
            "gross_salary",
            "net_salary",
            "salary_month",
            "payment_date",
            "employee_id",
        }
    ),
    AnalyzedDocumentType.ID_DOCUMENT: frozenset(
        {
            "full_name",
            "date_of_birth",
            "document_number",
            "nationality",
            "expiry_date",
        }
    ),
    AnalyzedDocumentType.TAX_DOCUMENT: frozenset(
        {
            "taxpayer_name",
            "tax_reference_number",
            "tax_year",
            "gross_income",
            "total_tax",
            "currency",
        }
    ),
    AnalyzedDocumentType.FORMAL_REQUEST_LETTER: frozenset(
        {
            "organization_name",
            "addressee",
            "subject",
            "date",
            "focal_person_name",
            "focal_person_designation",
        }
    ),
}

#: Fields whose absence forces the document into manual review regardless of
#: how the remaining checks scored. Scoped per document type for analysis
#: scoring — deliberately a separate set from `app.confidence.constants.
#: CRITICAL_FIELDS`, which is a flat global set gating human-review routing.
#: Keep both in sync by intent, not by identical membership.
CRITICAL_FIELDS: dict[AnalyzedDocumentType, frozenset[str]] = {
    AnalyzedDocumentType.BANK_STATEMENT: frozenset(
        {"account_number", "account_holder", "opening_balance", "closing_balance"}
    ),
    AnalyzedDocumentType.PAYSLIP: frozenset(
        {"employee_name", "gross_salary", "net_salary", "salary_month"}
    ),
    AnalyzedDocumentType.ID_DOCUMENT: frozenset(
        {"full_name", "date_of_birth", "document_number", "expiry_date"}
    ),
    AnalyzedDocumentType.TAX_DOCUMENT: frozenset(
        {"taxpayer_name", "tax_reference_number", "tax_year", "gross_income"}
    ),
    AnalyzedDocumentType.FORMAL_REQUEST_LETTER: frozenset(
        {"organization_name", "subject", "date"}
    ),
}
