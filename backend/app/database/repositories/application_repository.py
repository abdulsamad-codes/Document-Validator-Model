"""Repository for the Application entity."""

from collections.abc import Sequence

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.database.models.application import Application
from app.database.models.enums import ApplicationStatus
from app.database.repositories.base import BaseRepository, UNSET, _UnsetType


class ApplicationRepository(BaseRepository[Application]):
    """Persistence operations for :class:`Application`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[Application]:
        return Application

    def create(
        self,
        *,
        created_by: str,
        status: ApplicationStatus = ApplicationStatus.SUBMITTED,
        notes: str | None = None,
    ) -> Application:
        """Create and persist a new application.

        Args:
            created_by: Identifier of the user submitting the application.
            status: Initial application status.
            notes: Optional free-form notes.

        Returns:
            The persisted application with server-generated fields loaded.
        """
        application = Application(
            created_by=created_by,
            status=status,
            notes=notes,
        )
        self._db.add(application)
        return self._commit_and_refresh(application)

    def update(
        self,
        application: Application,
        *,
        status: ApplicationStatus | _UnsetType = UNSET,
        notes: str | None | _UnsetType = UNSET,
    ) -> Application:
        """Apply the provided changes to an application.

        Only arguments that were explicitly passed are applied; ``UNSET``
        fields remain untouched. Pass ``notes=None`` to clear the notes.

        Args:
            application: Application instance to update.
            status: New status, or :data:`UNSET` to leave unchanged.
            notes: New notes (``None`` clears them), or :data:`UNSET`.

        Returns:
            The updated application with server-generated fields loaded.
        """
        if status is not UNSET:
            application.status = status
        if notes is not UNSET:
            application.notes = notes
        self._db.add(application)
        return self._commit_and_refresh(application)

    def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        status: ApplicationStatus | None = None,
    ) -> Sequence[Application]:
        """List applications, optionally filtered by status.

        Args:
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.
            status: When given, only return applications in this status.

        Returns:
            A sequence of applications ordered by submission date.
        """
        statement = (
            select(Application)
            .order_by(Application.submitted_at.desc(), Application.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if status is not None:
            statement = statement.where(Application.status == status)
        return self._db.scalars(statement).all()

    def search(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        query: str | None = None,
        status: ApplicationStatus | None = None,
    ) -> tuple[Sequence[Application], int]:
        """Search applications by free-text query, optionally by status.

        The free-text query matches the application id (when the query parses
        as an integer), the display name and the submitter, so IT can find an
        application by ``123``, by ``TMA Khal Dir Lower`` or by the uploader's
        identifier alike.

        Args:
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.
            query: Free-text substring match against id/name/created_by.
            status: When given, only return applications in this status.

        Returns:
            A tuple of matching applications (newest first) and the total count.
        """
        statement = select(Application).order_by(
            Application.submitted_at.desc(), Application.id.desc()
        )
        statement = self._apply_filters(statement, query=query, status=status)
        total = len(self._db.scalars(statement.with_only_columns(Application.id)).all())
        rows = list(self._db.scalars(statement.offset(offset).limit(limit)).all())
        return rows, total

    @staticmethod
    def _apply_filters(
        statement: Select,
        *,
        query: str | None,
        status: ApplicationStatus | None,
    ) -> Select:
        """Apply the search filters to a select statement."""
        if status is not None:
            statement = statement.where(Application.status == status)
        if query:
            conditions = [
                Application.name.ilike(f"%{query}%"),
                Application.created_by.ilike(f"%{query}%"),
            ]
            if query.isdigit():
                conditions.append(Application.id == int(query))
            statement = statement.where(or_(*conditions))
        return statement
