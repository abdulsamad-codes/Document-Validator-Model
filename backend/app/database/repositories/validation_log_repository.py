"""Repository for the ValidationLog entity.

Log rows are immutable and append-only: this repository exposes creation and
read operations only -- no update, no delete. The create and bulk_create
methods flush but do not commit so the validation service can persist a state
transition and its accompanying log entries atomically.
"""

from collections.abc import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models.enums import (
    ValidationLogAction,
    ValidationLogCheckType,
    ValidationLogResult,
)
from app.database.models.validation_log import ValidationLog
from app.database.repositories.base import BaseRepository


class ValidationLogRepository(BaseRepository[ValidationLog]):
    """Persistence operations for :class:`ValidationLog`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[ValidationLog]:
        return ValidationLog

    def create(
        self,
        *,
        validation_task_id: int,
        application_id: int,
        action: ValidationLogAction,
        check_type: ValidationLogCheckType | None = None,
        field_name: str | None = None,
        previous_value: str | None = None,
        new_value: str | None = None,
        result: ValidationLogResult | None = None,
        reason: str | None = None,
        validation_run_id: int | None = None,
    ) -> ValidationLog:
        """Add a new immutable log entry without committing the transaction.

        Args:
            validation_task_id: Task the event belongs to.
            application_id: Application being validated.
            action: Kind of event that occurred.
            check_type: Kind of check the event refers to, when applicable.
            field_name: Field the event refers to, when applicable.
            previous_value: Value before the event, when applicable.
            new_value: Value after the event, when applicable.
            result: Outcome of the check, when applicable.
            reason: Free-form justification, when applicable.
            validation_run_id: Validation run the event belongs to.

        Returns:
            The pending log entry with server-generated fields loaded.
        """
        log = ValidationLog(
            validation_task_id=validation_task_id,
            application_id=application_id,
            validation_run_id=validation_run_id,
            action=action,
            check_type=check_type,
            field_name=field_name,
            previous_value=previous_value,
            new_value=new_value,
            result=result,
            reason=reason,
        )
        self._db.add(log)
        self._db.flush()
        self._db.refresh(log)
        return log

    def bulk_create(self, logs: Iterable[ValidationLog]) -> list[ValidationLog]:
        """Add multiple immutable log entries in one flush.

        Args:
            logs: Log instances to persist.

        Returns:
            The pending log entries with server-generated fields loaded.
        """
        entries = list(logs)
        if not entries:
            return []
        self._db.add_all(entries)
        self._db.flush()
        for entry in entries:
            self._db.refresh(entry)
        return entries

    def get_by_task(
        self,
        validation_task_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[ValidationLog]:
        """Return the log entries for a task, most recent first.

        Args:
            validation_task_id: Task id to look up.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A sequence of log entries.
        """
        statement = (
            select(ValidationLog)
            .where(ValidationLog.validation_task_id == validation_task_id)
            .order_by(
                ValidationLog.created_at.desc(),
                ValidationLog.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return self._db.scalars(statement).all()

    def get_by_application(
        self,
        application_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[ValidationLog]:
        """Return the log entries for an application, most recent first.

        Args:
            application_id: Application id to look up.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A sequence of log entries.
        """
        statement = (
            select(ValidationLog)
            .where(ValidationLog.application_id == application_id)
            .order_by(
                ValidationLog.created_at.desc(),
                ValidationLog.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return self._db.scalars(statement).all()

    def count_by_task(self, validation_task_id: int) -> int:
        """Return the number of log entries for a task.

        Args:
            validation_task_id: Task id to look up.

        Returns:
            The number of log entries for the task.
        """
        statement = select(func.count(ValidationLog.id)).where(
            ValidationLog.validation_task_id == validation_task_id
        )
        return self._db.execute(statement).scalar_one()

    def count_by_application(self, application_id: int) -> int:
        """Return the number of log entries for an application.

        Args:
            application_id: Application id to look up.

        Returns:
            The number of log entries for the application.
        """
        statement = select(func.count(ValidationLog.id)).where(
            ValidationLog.application_id == application_id
        )
        return self._db.execute(statement).scalar_one()
