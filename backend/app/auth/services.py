"""Business logic for authentication.

The service owns login, session lookup, token refresh and logout. It works
against the database repositories and the low-level security helpers, leaving
the route layer to translate the results into HTTP cookies and responses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.auth.exceptions import (
    AccountInactive,
    InvalidCredentials,
    InvalidRefreshToken,
    MissingCredentials,
    UserNotFound,
)
from app.auth.repositories import RefreshTokenRepository, UserRepository
from app.core.config import Settings, get_settings
from app.core.security import (
    TokenDecodeError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.database.models.user import User

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TokenPair:
    """An access token and its matching opaque refresh token."""

    access_token: str
    refresh_token: str
    refresh_expires_in: timedelta


class AuthenticationService:
    """Authentication operations bound to a database session.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._users = UserRepository(db)
        self._refresh_tokens = RefreshTokenRepository(db)

    def _issue_token_pair(self, user: User, settings: Settings) -> TokenPair:
        """Issue a fresh access token and a persisted opaque refresh token.

        Args:
            user: Authenticated user.
            settings: Application settings for token lifetimes.

        Returns:
            The access token, the new refresh token and its lifetime.
        """
        access_token = create_access_token(
            user.id,
            expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        )
        refresh_value = generate_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(
            days=settings.refresh_token_expire_days
        )
        self._refresh_tokens.create(
            user_id=user.id,
            token_hash=hash_token(refresh_value),
            expires_at=expires_at,
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_value,
            refresh_expires_in=timedelta(days=settings.refresh_token_expire_days),
        )

    def login(
        self,
        *,
        identifier: str,
        password: str,
        remember: bool,
    ) -> TokenPair:
        """Authenticate a user by employee id/email and issue a token pair.

        The ``remember`` flag only controls whether the refresh cookie persists
        across browser restarts (handled by the route layer); it does not change
        the server-side token lifetime.

        Args:
            identifier: Employee id or email.
            password: Plaintext password.
            remember: Whether the device should be remembered.

        Returns:
            A fresh token pair.

        Raises:
            InvalidCredentials: When the identifier or password is wrong.
            AccountInactive: When the account has been disabled.
        """
        settings = get_settings()
        user = self._users.get_by_identifier(identifier)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentials()
        if not user.is_active:
            raise AccountInactive()
        return self._issue_token_pair(user, settings)

    def refresh(self, refresh_token: str) -> TokenPair:
        """Validate a refresh token and issue a rotated token pair.

        The presented token is revoked before the replacement is issued so a
        captured token can never be replayed (rotation).

        Args:
            refresh_token: Opaque token from the refresh cookie.

        Returns:
            A fresh token pair.

        Raises:
            InvalidRefreshToken: When the token is unknown, revoked or expired.
            UserNotFound: When the owning user no longer exists.
        """
        settings = get_settings()
        record = self._refresh_tokens.get_active_by_hash(hash_token(refresh_token))
        if record is None:
            raise InvalidRefreshToken()
        user = self._users.get_by_id(record.user_id)
        if user is None:
            raise UserNotFound()
        if not user.is_active:
            raise AccountInactive()
        self._refresh_tokens.revoke(record)
        return self._issue_token_pair(user, settings)

    def logout(self, refresh_token: str | None) -> None:
        """Revoke a refresh token, making its session invalid.

        Args:
            refresh_token: Opaque token from the refresh cookie, if present.
        """
        if not refresh_token:
            return
        record = self._refresh_tokens.get_active_by_hash(hash_token(refresh_token))
        if record is not None:
            self._refresh_tokens.revoke(record)

    def get_user_by_access_token(self, access_token: str | None) -> User:
        """Resolve the user identified by a valid access token.

        Args:
            access_token: Signed JWT from the access cookie.

        Returns:
            The authenticated user.

        Raises:
            MissingCredentials: When no access token was provided.
            UserNotFound: When the token is invalid or its user is gone.
        """
        if not access_token:
            raise MissingCredentials()
        try:
            user_id = decode_access_token(access_token)
        except TokenDecodeError:
            raise UserNotFound() from None
        user = self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFound()
        if not user.is_active:
            raise AccountInactive()
        return user

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password for storage (used by the seed script and tests)."""
        return hash_password(password)
