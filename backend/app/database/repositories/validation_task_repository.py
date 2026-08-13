"""Repository for the ValidationTask entity.

The create and update methods flush but do not commit so the validation service
can group a task transition and its accompanying validation log into one atomic
transaction. ``get_by_id_locked`` acquires a PostgreSQL row lock so concurrent
state transitions (e.g. two starts on the same task) cannot race.
"""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models.enums import (
    ValidationTaskPriority,
    ValidationTaskStatus,
)
from app.database.models.validation_task import ValidationTask
from app.database.repositories.base import BaseRepository, UNSET, _UnsetType


class ValidationTaskRepository(BaseRepository[ValidationTask]):
    """Persistence operations for :class:`ValidationTask`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[ValidationTask]:
        return ValidationTask

    def create(
        self,
        *,
        application_id: int,
        validation_run_id: int | None,
        priority: ValidationTaskPriority = ValidationTaskPriority.NORMAL,
    ) -> ValidationTask:
        """Add a new validation task without committing the transaction.

        Args:
            application_id: Application being validated.
            validation_run_id: Validation run the task belongs to.
            priority: Scheduling priority of the task.

        Returns:
            The pending validation task with server-generated fields loaded.
        """
        task = ValidationTask(
            application_id=application_id,
            validation_run_id=validation_run_id,
            priority=priority,
        )
        self._db.add(task)
        self._db.flush()
        self._db.refresh(task)
        return task

    def update(
        self,
        task: ValidationTask,
        *,
        status: ValidationTaskStatus | _UnsetType = UNSET,
        started_at: object | _UnsetType = UNSET,
        completed_at: object | _UnsetType = UNSET,
    ) -> ValidationTask:
        """Apply the provided changes to a task without committing.

        Only arguments that were explicitly passed are applied; ``UNSET``
        fields remain untouched. Pass ``None`` to clear ``started_at`` or
        ``completed_at``.

        Args:
            task: Task instance to update.
            status: New status, or :data:`UNSET` to leave unchanged.
            started_at: New started-at value, or :data:`UNSET`.
            completed_at: New completed-at value, or :data:`UNSET`.

        Returns:
            The updated task with server-generated fields loaded.
        """
        if status is not UNSET:
            task.status = status
        if started_at is not UNSET:
            task.started_at = started_at
        if completed_at is not UNSET:
            task.completed_at = completed_at
        self._db.add(task)
        self._db.flush()
        self._db.refresh(task)
        return task

    def get_by_id_locked(self, task_id: int) -> ValidationTask | None:
        """Return a task, locking its row until the transaction commits.

        The ``SELECT ... FOR UPDATE`` guard prevents two concurrent requests
        from observing the same starting state and both performing a state
        transition on the same task.

        Args:
            task_id: Primary key of the task.

        Returns:
            The locked task or ``None`` when it does not exist.
        """
        statement = (
            select(ValidationTask)
            .where(ValidationTask.id == task_id)
            .with_for_update()
        )
        return self._db.scalars(statement).first()

    def get_active_for_application(self, application_id: int) -> ValidationTask | None:
        """Return the most recent non-terminal task for an application, if any.

        A task is active while it is PENDING or IN_REVIEW. Because corrected
        documents produce a brand new run/task, only one active task should
        exist per application at any moment; the service uses this guard when
        creating tasks.

        Args:
            application_id: Application id to look up.

        Returns:
            The most recent active task or ``None``.
        """
        statement = (
            select(ValidationTask)
            .where(
                ValidationTask.application_id == application_id,
                ValidationTask.status.in_(
                    [
                        ValidationTaskStatus.PENDING,
                        ValidationTaskStatus.IN_REVIEW,
                    ]
                ),
            )
            .order_by(ValidationTask.id.desc())
            .limit(1)
        )
        return self._db.scalars(statement).first()

    def list(
        self,
        *,
        status: ValidationTaskStatus | None = None,
        priority: ValidationTaskPriority | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[ValidationTask]:
        """Return tasks matching the filters, ordered for the queue.

        Rows are ordered by status, then priority and finally creation time so
        the queue surfaces the most urgent pending work first.

        Args:
            status: When given, only return tasks in this status.
            priority: When given, only return tasks of this priority.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A sequence of matching tasks.
        """
        statement = select(ValidationTask)
        if status is not None:
            statement = statement.where(ValidationTask.status == status)
        if priority is not None:
            statement = statement.where(ValidationTask.priority == priority)
        statement = statement.order_by(
            ValidationTask.status,
            ValidationTask.priority,
            ValidationTask.created_at.desc(),
            ValidationTask.id.desc(),
        )
        return self._db.scalars(
            statement.offset(offset).limit(limit)
        ).all()

    def count(
        self,
        *,
        status: ValidationTaskStatus | None = None,
        priority: ValidationTaskPriority | None = None,
    ) -> int:
        """Return the number of tasks matching the filters.

        Args:
            status: When given, only count tasks in this status.
            priority: When given, only count tasks of this priority.

        Returns:
            The number of matching tasks.
        """
        statement = select(func.count(ValidationTask.id))
        if status is not None:
            statement = statement.where(ValidationTask.status == status)
        if priority is not None:
            statement = statement.where(ValidationTask.priority == priority)
        return self._db.execute(statement).scalar_one()
