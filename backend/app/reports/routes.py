"""HTTP endpoints for the validation report module.

Exposes the report (``GET``), printable HTML report (``GET``) and condensed
summary (``GET``) endpoints. Routes stay thin: they build the service per
request and translate the module's domain exceptions into documented HTTP
errors.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.reports.exceptions import ReportError
from app.reports.schemas import (
    ErrorResponse,
    ValidationReport,
    ValidationSummary,
)
from app.reports.services import ValidationReportService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])

_GET_DB = Annotated[Session, Depends(get_db)]

#: Shared OpenAPI error-response documentation reused by every endpoint.
_ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Application not found."},
    422: {
        "model": ErrorResponse,
        "description": "Application has no validation results to report.",
    },
    500: {"model": ErrorResponse, "description": "Report generation failed."},
}


def _handle_report_errors(func):
    """Translate :class:`ReportError` into HTTP error responses.

    Keeps the error mapping inside the reports module while remaining
    compatible with FastAPI versions that do not expose router-level exception
    handlers.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ReportError as exc:
            logger.error(
                "Report error %s: %s",
                exc.__class__.__name__,
                exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return wrapper


def _service(db: Session) -> ValidationReportService:
    """Build the validation report service bound to the request session."""
    return ValidationReportService(db)


@router.get(
    "/applications/{application_id}/validation-report",
    response_model=ValidationReport,
    summary="Generate validation report",
    description=(
        "Aggregates the application's stored pipeline results -- documents, "
        "OCR, extracted fields, business and technical validation results and "
        "visual detections -- into a structured report for employee review. "
        "No validation or detection is re-run. The report is generated "
        "deterministically and can be regenerated at any time."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_report_errors
def get_validation_report(
    application_id: int,
    db: _GET_DB,
) -> ValidationReport:
    """Generate the full validation report for an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The structured validation report.

    Raises:
        HTTPException: When the application does not exist or has no
            validation results.
    """
    return _service(db).get_report(application_id=application_id)


@router.get(
    "/applications/{application_id}/validation-report/html",
    response_class=HTMLResponse,
    summary="Generate printable HTML validation report",
    description=(
        "Returns the same validation report rendered as a printable HTML "
        "document from a Jinja2 template, suitable for employee review and "
        "printing."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_report_errors
def get_validation_report_html(
    application_id: int,
    db: _GET_DB,
) -> HTMLResponse:
    """Render the printable HTML validation report for an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The rendered HTML document.

    Raises:
        HTTPException: When the application does not exist or has no
            validation results.
    """
    html = _service(db).render_html(application_id=application_id)
    return HTMLResponse(content=html, media_type="text/html")


@router.get(
    "/applications/{application_id}/validation-summary",
    response_model=ValidationSummary,
    summary="Generate validation summary",
    description=(
        "Returns a condensed version of the validation report with the "
        "headline totals and the overall status, for dashboards and list "
        "views."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_report_errors
def get_validation_summary(
    application_id: int,
    db: _GET_DB,
) -> ValidationSummary:
    """Generate the condensed validation summary for an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The condensed report.

    Raises:
        HTTPException: When the application does not exist or has no
            validation results.
    """
    return _service(db).get_summary(application_id=application_id)
