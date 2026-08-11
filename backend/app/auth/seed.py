"""Management script: seed the default employee account.

Run from the backend directory::

    python -m app.auth.seed

Creates (or updates) the default account whose credentials come from the
``DEFAULT_EMPLOYEE_*`` settings. Refuses to seed with the development default
password when the environment is production.

The script commits its own transaction and is safe to run repeatedly.
"""

import logging

from sqlalchemy import select

from app.auth.services import AuthenticationService
from app.core.config import Settings, get_settings
from app.database.connection import SessionLocal
from app.database.models.user import User

logger = logging.getLogger(__name__)

#: Password shipped as the development default.
_DEV_DEFAULT_PASSWORD = "Welcome@123"


def _load_or_create_user(db, settings: Settings) -> tuple[User, bool]:
    """Return the default user and whether it already existed."""
    existing = db.scalar(
        select(User).where(User.employee_id == settings.default_employee_id)
    )
    if existing is not None:
        return existing, True
    user = User(
        employee_id=settings.default_employee_id,
        email=settings.default_employee_email,
        name=settings.default_employee_name,
        role=settings.default_employee_role,
        password_hash=AuthenticationService.hash_password(
            settings.default_employee_password.get_secret_value()
        ),
    )
    db.add(user)
    return user, False


def seed() -> None:
    """Create or update the default employee account."""
    settings = get_settings()
    password = settings.default_employee_password.get_secret_value()

    if settings.environment == "production" and password == _DEV_DEFAULT_PASSWORD:
        raise SystemExit(
            "Refusing to seed: DEFAULT_EMPLOYEE_PASSWORD still uses the "
            "development default in a production environment."
        )

    db = SessionLocal()
    try:
        user, existed = _load_or_create_user(db, settings)
        if not existed:
            db.commit()
            logger.info(
                "Created default account %s (%s)",
                user.employee_id,
                user.email,
            )
        else:
            logger.info(
                "Account %s already exists; leaving it unchanged",
                user.employee_id,
            )
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    seed()
