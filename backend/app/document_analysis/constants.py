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
#: Phase 1 of the required-document checklist (see
    #: docs/IMPLEMENTATION_ROADMAP.md). Named identically to the storage-level
    #: DocumentType they correspond to, but distinct enums -- routed via
    #: document_analysis.services._CHECKLIST_TYPE_MAP, not via
    #: detect_document_type's keyword table.
    BILATERAL_AGREEMENT = "BILATERAL_AGREEMENT"
    AUTHORITY_LETTER = "AUTHORITY_LETTER"
    ACCOUNT_MAINTENANCE_CERTIFICATE = "ACCOUNT_MAINTENANCE_CERTIFICATE"
    TRIPARTITE_AGREEMENT = "TRIPARTITE_AGREEMENT"
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
#: Field names deliberately match app.rule_engine.rules.cross_document_rules
    #: (account_holder, account_number, iban): those rules are already
    #: registered and compare these exact names across BILATERAL_AGREEMENT,
    #: TRIPARTITE_AGREEMENT and ACCOUNT_MAINTENANCE_CERTIFICATE, but until now
    #: none of the three had any extractor, so the rules could only ever FAIL
    #: on a real application ("field is missing from document"). This is the
    #: first of the three to close that gap.
    AnalyzedDocumentType.BILATERAL_AGREEMENT: frozenset(
        {
            "organization_name",
            "platform_name",
            "transaction_charges",
            "account_holder",
            "account_number",
            "iban",
            "effective_date",
        }
    ),
    #: account_holder/account_number/iban are opportunistic, not guaranteed:
    #: docs/Master_Rules_Combined.md Section 2 says "account maintenance
    #: details must appear at the top", but neither real sample reviewed so
    #: far (two independent departments, Confidential Data/) carries any bank
    #: account information at all -- real evidence overrides the spec's
    #: framing here, see CRITICAL_FIELDS below.
    AnalyzedDocumentType.AUTHORITY_LETTER: frozenset(
        {
            "focal_person_name",
            "focal_person_designation",
            "organization_name",
            "account_holder",
            "account_number",
            "iban",
        }
    ),
    # Real required-document checklist categories with field-level extractors.
    # Field names deliberately match the cross-document consistency rules
    # (app/rule_engine/rules/cross_document_rules.py): account_holder,
    # account_number, iban, statement_period and branch_code must keep their
    # exact names so the normalization stage can compare them across
    # Bilateral / Tripartite / AMC documents.
    AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE: frozenset(
        {
            "account_holder",
            "account_number",
            "iban",
            "bank_name",
            "branch_name",
            "issue_date",
        }
    ),
    AnalyzedDocumentType.TRIPARTITE_AGREEMENT: frozenset(
        {
            "party_1link",
            "party_kpitb",
            "party_subbiller",
            "account_holder",
            "account_number",
            "branch_code",
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
#: organization_name, account_number and transaction_charges are the
    #: fields docs/Master_Rules_Combined.md explicitly calls "required content"
    #: for this document (Section 7). account_number is additionally critical
    #: because the cross-document consistency rules can never pass without it.
    AnalyzedDocumentType.BILATERAL_AGREEMENT: frozenset(
        {"organization_name", "account_number", "transaction_charges"}
    ),
    #: account_holder/account_number/iban deliberately excluded -- real
    #: evidence (two independent departments) shows Authority Letters
    #: routinely omit bank details entirely, despite the master-rules spec
    #: implying they're required; treating them as critical would force every
    #: real application into manual review for a field that's rarely there.
    AnalyzedDocumentType.AUTHORITY_LETTER: frozenset(
        {"focal_person_name", "focal_person_designation", "organization_name"}
    ),
    AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE: frozenset(
        {"account_holder", "account_number", "iban"}
    ),
    AnalyzedDocumentType.TRIPARTITE_AGREEMENT: frozenset(
        {"party_1link", "party_kpitb", "party_subbiller", "account_holder", "account_number"}
    ),
}
