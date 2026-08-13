"""Repository layer facade for the validation module.

Re-exports the repositories this module needs from the shared database layer so
the services depend on the module facade instead of importing repository paths
directly.
"""

from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.extracted_field_repository import (
    ExtractedFieldRepository,
)
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
from app.database.repositories.visual_detection_repository import (
    VisualDetectionRepository,
)

__all__ = [
    "ApplicationRepository",
    "ExtractedFieldRepository",
    "ValidationLogRepository",
    "ValidationRepository",
    "ValidationRunRepository",
    "ValidationTaskRepository",
    "VisualDetectionRepository",
]