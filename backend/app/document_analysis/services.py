"""Document analysis service.

Orchestrates the analysis pipeline for every document of an application: loads
the OCR text, detects the analysed document type, extracts structured fields,
validates them, runs the cross-field consistency rules, computes the
deterministic confidence score and verification status, and persists one
analysis result row per document. Per-document failures (missing OCR result,
undetermined type, extraction problems) are captured inside the response and
never abort the run.
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.database.models.document import Document
from app.database.models.document_analysis_result import DocumentAnalysisResult
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_analysis_repository import DocumentAnalysisRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.ocr_repository import OCRRepository
from app.core.config import get_settings
from app.document_analysis.constants import (
    ANALYSIS_VERSION,
    EXPECTED_FIELDS,
    AnalyzedDocumentType,
)
from app.document_analysis.exceptions import (
    ApplicationNotFound,
    DocumentAnalysisError,
    OCRResultNotFound,
    UnsupportedDocumentType,
)
from app.document_analysis.extractors import detect_document_type, extract_fields
from app.document_analysis.fallbacks import (
    AiFallbackMetrics,
    FieldFallback,
    fields_needing_ai,
    merge_fallback_values,
)
from app.document_analysis.rules import RulesEngine, scoring_components
from app.document_analysis.schemas import (
    AnalysisResultItem,
    AnalysisResultsResponse,
    AnalyzeDocumentsResponse,
    AnalysisOutcome,
    DocumentAnalysisItem,
)
from app.document_analysis.validators import ValidatorEngine

logger = logging.getLogger(__name__)

#: Default AI fallback provider factory. Production wiring assigns a factory
#: that returns a :class:`FieldFallback`; tests substitute a fake provider. The
#: module-level reference keeps the route layer thin (mirroring the OCR engine
#: factory pattern) while ``ai_fallback_enabled`` gates whether a provider is
#: ever consulted.
ai_fallback_factory: Callable[[], FieldFallback | None] | None = None


class DocumentAnalysisService:
    """Runs the analysis pipeline over an application's documents.

    Args:
        db: SQLAlchemy session used for all database interaction.
        fallback_factory: Optional factory producing an AI/VLM field fallback
            provider. When provided (and ``ai_fallback_enabled`` is true) the
            provider is consulted only for expected fields the rule pipeline
            left missing or invalid; when absent, AI is never called.
        metrics: Optional counter object recording AI fallback usage. Useful
            for benchmarks and tests; defaults to a private instance.
    """

    def __init__(
        self,
        db: Session,
        *,
        fallback_factory: Callable[[], FieldFallback | None] | None = None,
        metrics: AiFallbackMetrics | None = None,
    ) -> None:
        self._db = db
        self._applications = ApplicationRepository(db)
        self._documents = DocumentRepository(db)
        self._ocr_results = OCRRepository(db)
        self._analysis_results = DocumentAnalysisRepository(db)
        self._validators = ValidatorEngine()
        self._rules = RulesEngine()
        self._metrics = metrics or AiFallbackMetrics()
        if fallback_factory is not None:
            self._fallback = fallback_factory()
        elif get_settings().ai_fallback_enabled and ai_fallback_factory is not None:
            self._fallback = ai_fallback_factory()
        else:
            self._fallback = None

    @property
    def metrics(self) -> AiFallbackMetrics:
        """AI fallback usage counters of this service instance."""
        return self._metrics

    def analyze(self, *, application_id: int) -> AnalyzeDocumentsResponse:
        """Analyse every document of an application and persist the results.

        Each document's OCR text is turned into an explainable analysis result.
        Documents without an OCR result, with undeterminable types or with
        failing extraction are reported as failed; the run always completes.

        Args:
            application_id: Id of the application to analyse.

        Returns:
            The outcome of the analysis run for every document.

        Raises:
            ApplicationNotFound: When the application does not exist.
        """
        application = self._get_application(application_id)
        documents = list(self._documents.get_all_by_application(application_id))
        logger.info(
            "Document analysis started for application id=%s (%s documents)",
            application.id,
            len(documents),
        )
        items: list[DocumentAnalysisItem] = []
        for document in documents:
            items.append(self._analyze_document(application.id, document))

        analyzed = sum(item.outcome is AnalysisOutcome.ANALYZED for item in items)
        failed = sum(item.outcome is AnalysisOutcome.FAILED for item in items)
        logger.info(
            "Document analysis completed for application id=%s: "
            "%s analyzed, %s failed",
            application.id,
            analyzed,
            failed,
        )
        return AnalyzeDocumentsResponse(
            application_id=application.id,
            items=items,
            total_analyzed=analyzed,
            total_failed=failed,
        )

    def get_results(self, *, application_id: int) -> AnalysisResultsResponse:
        """Return every stored analysis result for an application.

        Args:
            application_id: Id of the application.

        Returns:
            The stored analysis results, ordered by document.

        Raises:
            ApplicationNotFound: When the application does not exist.
        """
        application = self._get_application(application_id)
        documents = {
            document.id: document
            for document in self._documents.get_all_by_application(application_id)
        }
        rows = self._analysis_results.get_by_application(application_id)
        items = [self._result_item(documents, row) for row in rows]
        logger.info(
            "Returned %s stored analysis results for application id=%s",
            len(items),
            application.id,
        )
        return AnalysisResultsResponse(
            application_id=application.id,
            items=items,
            total=len(items),
        )

    def _get_application(self, application_id: int):
        """Return the application or raise ``ApplicationNotFound``."""
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFound()
        return application

    def _analyze_document(
        self,
        application_id: int,
        document: Document,
    ) -> DocumentAnalysisItem:
        """Analyse one document and persist its analysis result.

        Args:
            application_id: Owning application id.
            document: Document to analyse.

        Returns:
            The per-document outcome, either analysed or failed.
        """
        started = time.perf_counter()
        try:
            ocr_result = self._ocr_results.get_by_document(document.id)
            if ocr_result is None:
                raise OCRResultNotFound()

            document_type = detect_document_type(ocr_result.raw_ocr_text)
            if document_type is AnalyzedDocumentType.UNKNOWN:
                logger.warning(
                    "Document type undetermined for document id=%s (application id=%s)",
                    document.id,
                    application_id,
                )
                raise UnsupportedDocumentType()

            fields = extract_fields(ocr_result.raw_ocr_text, document_type)
            validations = self._validators.run(document_type, fields)
            fields, validations = self._resolve_low_confidence_fields(
                document_type,
                text=ocr_result.raw_ocr_text,
                fields=fields,
                validations=validations,
            )
            consistency = self._rules.run(document_type, fields)
            (
                field_coverage,
                validation_rate,
                consistency_rate,
                score,
                status,
            ) = scoring_components(
                document_type,
                fields=fields,
                validation_results=validations,
                consistency_results=consistency,
            )
            elapsed_ms = int((time.perf_counter() - started) * 1000)

            self._analysis_results.upsert(
                application_id=application_id,
                document_id=document.id,
                document_type=document_type.value,
                extracted_fields=fields,
                validation_results=validations,
                consistency_results=consistency,
                confidence_score=score,
                verification_status=status.value,
                analysis_version=ANALYSIS_VERSION,
                processing_time_ms=elapsed_ms,
            )
            logger.info(
                "Analysis persisted for document id=%s (application id=%s): "
                "type=%s score=%.3f status=%s in %s ms "
                "(coverage=%.3f validation=%.3f consistency=%.3f)",
                document.id,
                application_id,
                document_type.value,
                score,
                status.value,
                elapsed_ms,
                field_coverage,
                validation_rate,
                consistency_rate,
            )
            invalid_count = sum(
                1 for result in validations if result["status"] == "invalid"
            )
            missing_count = sum(
                1 for result in validations if result["status"] == "missing"
            )
            if invalid_count or missing_count:
                logger.warning(
                    "Analysis of document id=%s reported %s invalid and %s missing "
                    "fields (application id=%s)",
                    document.id,
                    invalid_count,
                    missing_count,
                    application_id,
                )
            return DocumentAnalysisItem(
                document_id=document.id,
                file_name=document.original_filename,
                document_type=document_type.value,
                outcome=AnalysisOutcome.ANALYZED,
                verification_status=status.value,
                confidence_score=score,
                extracted_fields=fields,
                validation_results=validations,
                consistency_results=consistency,
                issues=self._issues(validations, consistency),
                processing_time_ms=elapsed_ms,
            )
        except DocumentAnalysisError as exc:
            logger.error(
                "Analysis failed for document id=%s (application id=%s): %s",
                document.id,
                application_id,
                exc.detail,
            )
            return self._fail_item(document, exc.detail)
        except Exception as exc:  # pragma: no cover - defensive isolation
            logger.exception(
                "Analysis failed unexpectedly for document id=%s (application id=%s)",
                document.id,
                application_id,
            )
            return self._fail_item(document, f"Unexpected analysis error: {exc}")

    def _resolve_low_confidence_fields(
        self,
        document_type: AnalyzedDocumentType,
        *,
        text: str,
        fields: dict[str, Any],
        validations: list[dict[str, str]],
    ) -> tuple[dict[str, Any], list[dict[str, str]]]:
        """Consult the AI fallback for missing/invalid expected fields only.

        The rule pipeline runs first and its results are kept. When a fallback
        provider is configured (``ai_fallback_enabled`` and a factory), the
        provider is invoked once per document with just the names of the fields
        the rules left missing or invalid; resolved values are merged back and
        the affected validations are recomputed so scoring reflects the merged
        fields. With no provider configured the fields pass through untouched
        and no AI call is ever made.

        Args:
            document_type: Analysed document type.
            text: Raw document text (context for the provider).
            fields: Rule-extracted fields.
            validations: Per-field validation outcomes.

        Returns:
            The (possibly merged) fields and their recomputed validations.
        """
        needing = fields_needing_ai(
            fields,
            validations,
            EXPECTED_FIELDS.get(document_type, frozenset()),
        )
        self._metrics.fields_requiring_ai += len(needing)
        if not needing or self._fallback is None:
            return fields, validations

        self._metrics.ai_calls += 1
        self._metrics.fields_requested += len(needing)
        try:
            resolved = self._fallback.resolve(
                document_type=document_type,
                text=text,
                fields=fields,
                field_names=needing,
            )
        except Exception as exc:  # defensive isolation: AI must never break analysis
            self._metrics.failed_calls += 1
            logger.warning(
                "AI fallback failed for document type=%s fields=%s: %s",
                document_type.value,
                needing,
                exc,
            )
            return fields, validations

        merged = merge_fallback_values(fields, resolved or {}, needing)
        # Count fields the provider actually resolved: ones it added or whose
        # value it changed (an invalid-but-present field corrected by AI).
        resolved_names = sorted(
            name
            for name in needing
            if name in merged
            and (name not in fields or fields[name] != merged[name])
        )
        self._metrics.fields_resolved += len(resolved_names)
        if not resolved_names:
            return fields, validations
        logger.info(
            "AI fallback resolved %s field(s) for document type=%s: %s",
            len(resolved_names),
            document_type.value,
            resolved_names,
        )
        return merged, self._validators.run(document_type, merged)

    def _fail_item(self, document: Document, message: str) -> DocumentAnalysisItem:
        """Build a failed outcome for a document."""
        return DocumentAnalysisItem(
            document_id=document.id,
            file_name=document.original_filename,
            outcome=AnalysisOutcome.FAILED,
            message=message,
        )

    def _result_item(
        self,
        documents: dict[int, Document],
        row: DocumentAnalysisResult,
    ) -> AnalysisResultItem:
        """Map a stored analysis row onto its response schema.

        Args:
            documents: Application documents keyed by id.
            row: Stored analysis result.

        Returns:
            The serialized result item.
        """
        document = documents.get(row.document_id)
        validations = row.validation_results or []
        consistency = row.consistency_results or []
        return AnalysisResultItem(
            document_id=row.document_id,
            file_name=document.original_filename if document else "unknown",
            document_type=row.document_type,
            verification_status=row.verification_status,
            confidence_score=row.confidence_score,
            extracted_fields=row.extracted_fields,
            validation_results=validations,
            consistency_results=consistency,
            issues=self._issues(validations, consistency),
            processing_time_ms=row.processing_time_ms,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _issues(
        validations: list[dict],
        consistency: list[dict],
    ) -> list[str]:
        """Collect every non-passing validation and consistency message."""
        issues = [v["message"] for v in validations if v.get("status") != "valid"]
        issues += [c["message"] for c in consistency if c.get("status") != "pass"]
        return issues
