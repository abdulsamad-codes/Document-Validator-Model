"""Repository for the AuditLog entity."""

from typing import Any

from sqlalchemy.orm import Session

from app.database.models.audit_log import AuditLog
from app.database.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    """Persistence operations for :class:`AuditLog`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[AuditLog]:
        return AuditLog

    def create(
        self,
        *,
        application_id: int | None,
        username: str,
        action: str,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Create and persist a new audit log entry.

        Args:
            application_id: Related application, if any.
            username: Identity of the user who performed the action.
            action: Machine-readable action identifier.
            details: Structured JSON context describing the action.

        Returns:
            The persisted audit log entry.
        """
        entry = AuditLog(
            application_id=application_id,
            username=username,
            action=action,
            details=details,
        )
        self._db.add(entry)
        return self._commit_and_refresh(entry)
