"""FastAPI dependencies for authentication and role authorization."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.constants import ACCESS_TOKEN_COOKIE
from app.auth.roles import ROLES, effective_role
from app.auth.services import AuthenticationService
from app.database.connection import get_db
from app.database.models.user import User

_DB = Annotated[Session, Depends(get_db)]


def get_current_user(db: _DB, request: Request) -> User:
    """Resolve the authenticated user from the access-token cookie.

    Raises a 401 (via the route error handler) when the cookie is missing,
    expired, invalid, or refers to a deactivated/removed user.

    Args:
        db: Active database session.
        request: Incoming request whose cookies are inspected.

    Returns:
        The authenticated user.
    """
    service = AuthenticationService(db)
    return service.get_user_by_access_token(request.cookies.get(ACCESS_TOKEN_COOKIE))


def require_role(*roles: str) -> Callable:
    """Build a FastAPI dependency requiring the user to hold any listed role.

    The dependency resolves the authenticated user via :func:`get_current_user`
    (so a missing/expired session still yields 401) and then enforces the role
    against the user's effective role (:func:`app.auth.roles.effective_role`,
    which normalizes legacy role strings). A user who holds none of the
    requested roles receives ``403 Forbidden``.

    Usage::

        @router.post("/...", dependencies=[Depends(require_role(ROLE_OPERATOR))])
        def handle(...): ...

    Args:
        *roles: Role strings the user must hold (any of them). Unrecognized
            role names are rejected at import time to catch typos.

    Returns:
        A FastAPI dependency callable yielding the authenticated user.
    """
    for role in roles:
        if role not in ROLES:
            raise ValueError(f"Unknown role requested: {role!r}")
    requested = frozenset(roles)

    def _require_role(current_user: User = Depends(get_current_user)) -> User:
        if effective_role(current_user.role) not in requested:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return _require_role
