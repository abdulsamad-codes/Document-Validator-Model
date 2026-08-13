"""Repository for the ValidationRun entity.

Unlike the shared ``BaseRepository``, the create method here flushes but does
not commit: the validation service owns the transaction so a run, its task and
its initial log are persisted atomically in one commit.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models.validation_run import ValidationRun
from app.database.repositories.base import BaseRepository


class ValidationRunRepository(BaseRepository[ValidationRun]):
    """Persistence operations for :class:`ValidationRun`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[ValidationRun]:
        return ValidationRun

    def create(
        self,
        *,
        application_id: int,
        run_number: int,
    ) -> ValidationRun:
        """Add a new validation run without committing the transaction.

        Args:
            application_id: Application being validated.
            run_number: 1-based version number of the pass.

        Returns:
            The pending validation run with server-generated fields loaded.
        """
        run = ValidationRun(
            application_id=application_id,
            run_number=run_number,
        )
        self._db.add(run)
        self._db.flush()
        self._db.refresh(run)
        return run

    def next_run_number(self, application_id: int) -> int:
        """Return the next run number for an application.

        Args:
            application_id: Application id to look up.

        Returns:
            The highest run number for the application plus one (1 when the
            application has no previous runs).
        """
        statement = select(func.max(ValidationRun.run_number)).where(
            ValidationRun.application_id == application_id
        )
        current = self._db.execute(statement).scalar_one()
        return (current or 0) + 1

    def get_latest_for_application(
        self,
        application_id: int,
    ) -> ValidationRun | None:
        """Return the most recent validation run for an application, if any.

        Args:
            application_id: Application id to look up.

        Returns:
            The most recent run or ``None`` when the application has none.
        """
        statement = (
            select(ValidationRun)
            .where(ValidationRun.application_id == application_id)
            .order_by(ValidationRun.run_number.desc(), ValidationRun.id.desc())
            .limit(1)
        )
        return self._db.scalars(statement).first()
