"""Repository layer package.

Re-exports every repository so callers can import them from
``app.database.repositories`` in a single statement.
"""

from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.feedback_repository import FeedbackRepository
from app.database.repositories.human_correction_repository import (
    HumanCorrectionRepository,
)
from app.database.repositories.human_review_repository import HumanReviewRepository
from app.database.repositories.manual_checklist_repository import (
    ManualChecklistRepository,
)
from app.database.repositories.ocr_repository import OCRRepository
from app.database.repositories.validation_log_repository import (
    ValidationLogRepository,
)
from app.database.repositories.validation_repository import ValidationRepository
from app.database.repositories.validation_run_repository import (
    ValidationRunRepository,
)
from app.database.repositories.validation_task_repository import (
    ValidationTaskRepository,
)

__all__ = [
    "ApplicationRepository",
    "DocumentRepository",
    "FeedbackRepository",
    "HumanCorrectionRepository",
    "HumanReviewRepository",
    "ManualChecklistRepository",
    "OCRRepository",
    "ValidationLogRepository",
    "ValidationRepository",
    "ValidationRunRepository",
    "ValidationTaskRepository",
]
