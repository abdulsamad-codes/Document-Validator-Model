"""API package.

Aggregates every versioned router into a single ``api_router`` that the FastAPI
application mounts under the configured API prefix. Future feature routers
(auth, upload, validation, etc.) are registered here so the application factory
does not need to change when new endpoints are added.
"""

from fastapi import APIRouter

from app.api.health import router as health_router
from app.auth.routes import router as auth_router
from app.completeness.routes import router as completeness_router
from app.confidence.routes import router as confidence_router
from app.continuous_learning.routes import router as continuous_learning_router
from app.document_analysis.routes import router as document_analysis_router
from app.document_processing.routes import router as document_processing_router
from app.feedback.routes import router as feedback_router
from app.human_verification.routes import router as human_verification_router
from app.normalization.routes import router as normalization_router
from app.reports.routes import router as reports_router
from app.rule_engine.routes import router as rule_engine_router
from app.technical_validation.routes import router as technical_validation_router
from app.upload.routes import router as upload_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(upload_router)
api_router.include_router(completeness_router)
api_router.include_router(technical_validation_router)
api_router.include_router(document_processing_router)
api_router.include_router(document_analysis_router)
api_router.include_router(confidence_router)
api_router.include_router(normalization_router)
api_router.include_router(rule_engine_router)
api_router.include_router(reports_router)
api_router.include_router(human_verification_router)
api_router.include_router(feedback_router)
api_router.include_router(continuous_learning_router)

__all__ = ["api_router"]
