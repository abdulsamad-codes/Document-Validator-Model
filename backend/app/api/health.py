"""System health endpoints.

Provides liveness and readiness information used by operators and infrastructure
(e.g. container health checks). The endpoints must never raise on transient
infrastructure failures; instead they report a degraded status so monitoring can
react without taking the application down.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import get_settings
from app.database.connection import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    summary="Health check",
    description="Reports application liveness and database connectivity.",
)
def health_check(db: Session = Depends(get_db)) -> dict[str, str]:
    """Return the service health status.

    Verifies database connectivity with a trivial ``SELECT 1`` statement. A
    database failure is reported as a ``degraded`` status rather than an HTTP
    error, because the application process itself remains available.

    Args:
        db: Active database session injected by FastAPI.

    Returns:
        A mapping describing service name, environment and health status.
    """
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Health check failed to reach the database")
        return {
            "status": "degraded",
            "service": settings.app_name,
            "environment": settings.environment,
            "version": __version__,
        }

    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "version": __version__,
    }
