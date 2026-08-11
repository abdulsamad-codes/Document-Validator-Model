"""FastAPI dependencies for authentication."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.constants import ACCESS_TOKEN_COOKIE
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
