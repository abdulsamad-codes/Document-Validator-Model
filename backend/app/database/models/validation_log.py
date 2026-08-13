"""Validation log model.

Append-only audit trail for every important event that occurs during a
validation workflow. Log rows are immutable by design: corrections and
validation decisions create new rows and never overwrite existing history, so
the final validation result stays fully traceable. No user/operator fields
exist yet -- the separate User/Operator module will attach the acting operator
through a future migration.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.enums import (
    ValidationLogAction,
    ValidationLogCheckType,
    ValidationLogResult,
)

if TYPE_CHECKING:
    from app.database.models.application import Application
    from app.database.models.validation_run import ValidationRun
    from app.database.models.validation_task import ValidationTask


class ValidationLog(Base):
    """One immutable event recorded during a validation workflow.

    Attributes:
        id: Auto-incrementing primary key.
        validation_task_id: Task the event belongs to (foreign key, cascades).
        application_id: Application being validated (foreign key, cascades).
        validation_run_id: Validation run the event belongs to, or ``None``.
        action: Kind of event that occurred.
        check_type: Kind of check the event refers to, when applicable.
        field_name: Field the event refers to, when applicable.
        previous_value: Value before the event (e.g. original extracted value).
        new_value: Value after the event (e.g. corrected value).
        result: Outcome of the check, when applicable.
        reason: Free-form justification or note attached to the event.
        created_at: When the event was recorded (UTC).
    """

    __tablename__ = "validation_logs"
    __table_args__ = (
        Index("ix_validation_logs_validation_task_id", "validation_task_id"),
        Index("ix_validation_logs_application_id", "application_id"),
        Index("ix_validation_logs_validation_run_id", "validation_run_id"),
        Index("ix_validation_logs_created_at", "created_at"),
        Index("ix_validation_logs_action", "action"),
        Index("ix_validation_logs_check_type", "check_type"),
        Index(
            "ix_validation_logs_task_created_at",
            "validation_task_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    validation_task_id: Mapped[int] = mapped_column(
        ForeignKey("validation_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    validation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("validation_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[ValidationLogAction] = mapped_column(nullable=False)
    check_type: Mapped[ValidationLogCheckType | None] = mapped_column(nullable=True)
    field_name: Mapped[str | None] = mapped_column(Text)
    previous_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    result: Mapped[ValidationLogResult | None] = mapped_column(nullable=True)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    task: Mapped[ValidationTask] = relationship(back_populates="logs")
    application: Mapped[Application] = relationship(back_populates="validation_logs")
    validation_run: Mapped[ValidationRun | None] = relationship(
        back_populates="logs"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ValidationLog id={self.id} action={self.action}>"