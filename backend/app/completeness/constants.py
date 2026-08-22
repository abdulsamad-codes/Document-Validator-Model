"""Configuration for the document completeness module.

The canonical classification of document types into mandatory and optional
categories lives here and nowhere else. Verification logic consumes these sets
so adding a document type only requires editing this module, never the service,
route or schema code.
"""

from enum import Enum

from app.database.models.enums import DocumentType


class CompletenessStatus(str, Enum):
    """Overall outcome of a completeness verification.

    The precedence is strictest-first: an invalid document set always wins over
    duplicates, which win over incompleteness.
    """

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    DUPLICATE_DOCUMENTS = "DUPLICATE_DOCUMENTS"
    INVALID_DOCUMENT_SET = "INVALID_DOCUMENT_SET"


#: Document types every application must provide exactly once.
#:
#: SCHEDULE_OF_CHARGES deliberately removed 2026-08-22: real-world evidence
#: (every candidate real sample found so far, including every file whose name
#: suggested this type) confirms it is not a real standalone document in this
#: checklist -- its content (the Payment Methods & Charges clause) lives
#: inside the Bilateral Agreement, which already has its own real extractor
#: (BilateralAgreementExtractor.transaction_charges) and its own required
#: presence check above. See CONTEXT.md for the full decision record.
REQUIRED_DOCUMENT_TYPES: frozenset[DocumentType] = frozenset(
    {
        DocumentType.TRIPARTITE_AGREEMENT,
        DocumentType.BILATERAL_AGREEMENT,
        DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
        DocumentType.ONE_LINK_LETTER,
        DocumentType.AUTHORITY_LETTER,
        DocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
        DocumentType.FORMAL_REQUEST_LETTER,
    }
)

#: Document types an application may provide but does not have to.
OPTIONAL_DOCUMENT_TYPES: frozenset[DocumentType] = frozenset(
    {
        DocumentType.OTHER_SUPPORTING_DOCUMENT,
    }
)

#: Document types that are internal processing artifacts rather than real
#: onboarding documents (e.g. the BULK_UPLOAD placeholder that holds a bulk
#: PDF until it is split). They are recognised -- never flagged as unexpected
#: -- but contribute nothing to required or optional presence.
PLACEHOLDER_DOCUMENT_TYPES: frozenset[DocumentType] = frozenset(
    {
        DocumentType.BULK_UPLOAD,
    }
)

#: Every document type the pipeline recognises (required plus optional plus
#: placeholders). Any document type outside this set is treated as unexpected.
ALL_CONFIGURED_DOCUMENT_TYPES: frozenset[DocumentType] = (
    REQUIRED_DOCUMENT_TYPES | OPTIONAL_DOCUMENT_TYPES | PLACEHOLDER_DOCUMENT_TYPES
)
