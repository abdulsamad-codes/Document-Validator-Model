"""Audit log model.

Append-only record of important system actions. Audit logs deliberately use a
``SET NULL`` foreign key so records survive the deletion of the application they
reference; logs are never cascade-deleted. Structured details are stored as
JSONB so different actions can capture arbitrary, schema-free context.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.application import Application


class AuditLog(Base):
    """An auditable record of a system action.

    Attributes:
        id: Auto-incrementing primary key.
        application_id: Related application, if any (``SET NULL`` on delete).
        username: Identity of the user who performed the action.
        action: Machine-readable action identifier.
        performed_at: When the action occurred (UTC).
        details: Structured JSON context describing the action.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_application_id", "application_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
    )
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    application: Mapped[Application | None] = relationship(back_populates="audit_logs")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AuditLog id={self.id} action={self.action}>"
