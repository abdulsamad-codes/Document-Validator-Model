"""Domain enums shared by the ORM models.

Each enum maps to a native PostgreSQL ``ENUM`` type via SQLAlchemy. Native enum
types enforce allowed values at the database level (data integrity) while the
Python ``Enum`` classes keep the values strongly typed in application code. The
enum type name derives from the class name in lower case; when a new value is
added to an enum that already exists in a production database, a dedicated
migration must ``ALTER TYPE`` the enum.
"""

from enum import Enum


class ApplicationStatus(str, Enum):
    """Lifecycle state of a verification application."""

    SUBMITTED = "SUBMITTED"
    PROCESSING = "PROCESSING"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CORRECTED = "CORRECTED"


class DocumentType(str, Enum):
    """Document categories accepted by the verification pipeline.

    The values mirror the checklist item families (signatures and stamps) that
    are verified for each financial document.
    """

    TRIPARTITE_AGREEMENT = "TRIPARTITE_AGREEMENT"
    BILATERAL_AGREEMENT = "BILATERAL_AGREEMENT"
    ACCOUNT_MAINTENANCE_CERTIFICATE = "ACCOUNT_MAINTENANCE_CERTIFICATE"
    ONE_LINK_LETTER = "ONE_LINK_LETTER"
    AUTHORITY_LETTER = "AUTHORITY_LETTER"
    SCHEDULE_OF_CHARGES = "SCHEDULE_OF_CHARGES"
    BUSINESS_REQUIREMENT_DOCUMENT = "BUSINESS_REQUIREMENT_DOCUMENT"
    FORMAL_REQUEST_LETTER = "FORMAL_REQUEST_LETTER"
    OTHER_SUPPORTING_DOCUMENT = "OTHER_SUPPORTING_DOCUMENT"
    CNIC_FRONT = "CNIC_FRONT"
    CNIC_BACK = "CNIC_BACK"


class DocumentProcessingStatus(str, Enum):
    """State of a document within the processing pipeline."""

    UPLOADED = "UPLOADED"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ValidationStatus(str, Enum):
    """Outcome of a validation rule check."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    PENDING_MANUAL_REVIEW = "PENDING_MANUAL_REVIEW"


class Severity(str, Enum):
    """Importance level of a validation result."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ReviewDecision(str, Enum):
    """Decision taken by a human reviewer."""

    APPROVE = "APPROVE"
    CORRECT = "CORRECT"
    REJECT = "REJECT"


class ValidationTaskStatus(str, Enum):
    """Lifecycle state of a validation task.

    A task walks PENDING -> IN_REVIEW before reaching a terminal decision
    (VALIDATED, REJECTED) or being returned for correction
    (NEEDS_CORRECTION). NEEDS_CORRECTION is terminal for the current run: the
    corrected documents trigger a brand new task/run instead of reopening this
    one, so the historical result is never overwritten.
    """

    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    NEEDS_CORRECTION = "NEEDS_CORRECTION"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"


class ValidationTaskPriority(str, Enum):
    """Scheduling priority of a validation task."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ValidationLogAction(str, Enum):
    """Every kind of event the validation log can record.

    Log rows are append-only; each event creates a new row so the full
    validation history stays available for audit.
    """

    TASK_CREATED = "TASK_CREATED"
    TASK_STARTED = "TASK_STARTED"
    FIELD_VERIFIED = "FIELD_VERIFIED"
    FIELD_CORRECTED = "FIELD_CORRECTED"
    BUSINESS_RULE_REVIEWED = "BUSINESS_RULE_REVIEWED"
    SIGNATURE_REVIEWED = "SIGNATURE_REVIEWED"
    STAMP_REVIEWED = "STAMP_REVIEWED"
    ORIGINALITY_REVIEWED = "ORIGINALITY_REVIEWED"
    DOCUMENT_REVIEWED = "DOCUMENT_REVIEWED"
    CORRECTION_REQUESTED = "CORRECTION_REQUESTED"
    VALIDATION_COMPLETED = "VALIDATION_COMPLETED"
    VALIDATION_REJECTED = "VALIDATION_REJECTED"
    REVALIDATION_STARTED = "REVALIDATION_STARTED"


class ValidationLogCheckType(str, Enum):
    """Kind of check a validation log entry refers to."""

    ACCOUNT_NUMBER = "ACCOUNT_NUMBER"
    NTN = "NTN"
    BANK_NAME = "BANK_NAME"
    ACCOUNT_TITLE = "ACCOUNT_TITLE"
    SIGNATURE = "SIGNATURE"
    STAMP = "STAMP"
    BUSINESS_RULE = "BUSINESS_RULE"
    BANK_MAINTENANCE_ORIGINALITY = "BANK_MAINTENANCE_ORIGINALITY"
    DOCUMENT_REVIEW = "DOCUMENT_REVIEW"
    GENERAL = "GENERAL"


class ValidationLogResult(str, Enum):
    """Outcome recorded on a validation log entry."""

    PASS = "PASS"
    FAIL = "FAIL"
    CONFIRMED = "CONFIRMED"
    CORRECTED = "CORRECTED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    REJECTED = "REJECTED"
    REVIEWED = "REVIEWED"
    INFO = "INFO"
