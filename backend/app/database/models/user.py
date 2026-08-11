"""User model.

Represents a person who can sign in to the portal. Employees authenticate with
an employee ID or email plus a password; only their password hash is stored,
never the plaintext. Passwords are hashed with bcrypt via ``app.core.security``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.refresh_token import RefreshToken


class User(Base):
    """A portal user able to authenticate.

    Attributes:
        id: Auto-incrementing primary key.
        employee_id: Unique human-readable employee identifier (e.g. ``EMP-1001``).
        email: Unique work email used as an alternative login identifier.
        name: Display name.
        role: Job role shown in the UI.
        password_hash: Bcrypt hash of the user's password.
        is_active: Whether the account can sign in.
        created_at: When the user was created (UTC).
        updated_at: When the user was last modified (UTC).
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
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

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User id={self.id} employee_id={self.employee_id}>"
