"""Validation task model.

A validation task is the unit of work the validation queue hands to an operator
in a later phase: it tracks one validation workflow/run for an application
through PENDING, IN_REVIEW, NEEDS_CORRECTION, VALIDATED and REJECTED. No
user/operator fields exist yet -- the separate User/Operator module will attach
an assigned operator through a future migration.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.enums import (
    ValidationTaskPriority,
    ValidationTaskStatus,
)

if TYPE_CHECKING:
    from app.database.models.application import Application
    from app.database.models.validation_log import ValidationLog
    from app.database.models.validation_run import ValidationRun


class ValidationTask(Base):
    """A single validation workflow/run for an application.

    Attributes:
        id: Auto-incrementing primary key.
        application_id: Application being validated (foreign key, cascades).
        status: Current lifecycle state of the task.
        priority: Scheduling priority of the task.
        validation_run_id: Validation run this task belongs to, or ``None``.
        created_at: When the task was created (UTC).
        updated_at: When the task was last modified (UTC).
        started_at: When validation actually began (UTC).
        completed_at: When validation reached a terminal decision (UTC).
    """

    __tablename__ = "validation_tasks"
    __table_args__ = (
        Index("ix_validation_tasks_application_id", "application_id"),
        Index("ix_validation_tasks_status", "status"),
        Index("ix_validation_tasks_priority", "priority"),
        Index("ix_validation_tasks_created_at", "created_at"),
        Index("ix_validation_tasks_queue", "status", "priority", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[ValidationTaskStatus] = mapped_column(
        default=ValidationTaskStatus.PENDING,
        server_default=text("'PENDING'"),
        nullable=False,
    )
    priority: Mapped[ValidationTaskPriority] = mapped_column(
        default=ValidationTaskPriority.NORMAL,
        server_default=text("'NORMAL'"),
        nullable=False,
    )
    validation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("validation_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    application: Mapped[Application] = relationship(back_populates="validation_tasks")
    validation_run: Mapped[ValidationRun | None] = relationship(
        back_populates="tasks"
    )
    logs: Mapped[list[ValidationLog]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ValidationTask id={self.id} status={self.status}>"
