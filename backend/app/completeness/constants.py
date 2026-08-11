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
REQUIRED_DOCUMENT_TYPES: frozenset[DocumentType] = frozenset(
    {
        DocumentType.TRIPARTITE_AGREEMENT,
        DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
        DocumentType.ONE_LINK_LETTER,
        DocumentType.AUTHORITY_LETTER,
        DocumentType.SCHEDULE_OF_CHARGES,
        DocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
        DocumentType.FORMAL_REQUEST_LETTER,
    }
)

#: Document types an application may provide but does not have to.
OPTIONAL_DOCUMENT_TYPES: frozenset[DocumentType] = frozenset(
    {
        DocumentType.BILATERAL_AGREEMENT,
        DocumentType.OTHER_SUPPORTING_DOCUMENT,
    }
)

#: Every document type the pipeline recognises (required plus optional). Any
#: document type outside this set is treated as unexpected.
ALL_CONFIGURED_DOCUMENT_TYPES: frozenset[DocumentType] = (
    REQUIRED_DOCUMENT_TYPES | OPTIONAL_DOCUMENT_TYPES
)
