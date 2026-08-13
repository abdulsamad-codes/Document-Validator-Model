"""Validation run model.

Represents one versioned validation pass over an application. Every time the
automated pipeline finishes (including after a correction has been processed),
a new run is created with an incremented ``run_number`` so the historical runs
are never overwritten. Validation tasks and validation logs reference the run
that produced them.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.application import Application
    from app.database.models.validation_log import ValidationLog
    from app.database.models.validation_task import ValidationTask


class ValidationRun(Base):
    """A single numbered validation pass for an application.

    Attributes:
        id: Auto-incrementing primary key.
        application_id: Application being validated (foreign key, cascades).
        run_number: 1-based version number of this pass within the application.
        created_at: When the run was recorded (UTC).
    """

    __tablename__ = "validation_runs"
    __table_args__ = (
        Index("ix_validation_runs_application_id", "application_id"),
        UniqueConstraint(
            "application_id",
            "run_number",
            name="uq_validation_runs_application_id_run_number",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    application: Mapped[Application] = relationship(back_populates="validation_runs")
    tasks: Mapped[list[ValidationTask]] = relationship(
        back_populates="validation_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    logs: Mapped[list[ValidationLog]] = relationship(
        back_populates="validation_run",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ValidationRun id={self.id} app={self.application_id} run={self.run_number}>"
