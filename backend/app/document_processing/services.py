"""Document processing service.

Orchestrates the extraction pipeline for every document of an application:
enforces the technical validation gate, routes each document to the right
extractor, persists one OCR result row per document (reusing the Phase 2 OCR
results table) and reads stored results back. Per-document failures are captured
inside the response and never abort the run.
"""

import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models.document import Document
from app.database.models.enums import DocumentProcessingStatus, ValidationStatus
from app.database.models.ocr_result import OCRResult
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.ocr_repository import OCRRepository
from app.document_processing.constants import (
    PROCESSING_TIMEOUT_SECONDS,
    DocumentSource,
)
from app.document_processing.exceptions import (
    ApplicationNotFound,
    DocumentProcessingError,
    TechnicalValidationRequired,
)
from app.document_processing.processors import (
    DigitalPdfExtractor,
    ExtractionResult,
    ImageExtractor,
    OCREngine,
    ScannedPdfExtractor,
    _create_ocr_engine,
)
from app.document_processing.schemas import (
    DocumentProcessingResult,
    OcrResultItem,
    OcrResultsResponse,
    ProcessDocumentsResponse,
    ProcessingOutcome,
)
from app.document_processing.validators import (
    assert_non_empty_text,
    classify_document_source,
    detect_format,
    resolve_document_file,
)
from app.technical_validation.services import TechnicalValidationService
from app.upload.storage import StorageService

logger = logging.getLogger(__name__)

#: Default OCR engine factory. Tests swap this module-level reference for a fake
#: engine so the pipeline runs without downloading OCR models.
ocr_engine_factory: Callable[[], OCREngine] = _create_ocr_engine


class DocumentProcessingService:
    """Routes and executes text extraction for an application's documents.

    Args:
        db: SQLAlchemy session used for all database interaction.
        engine_factory: Optional factory producing the OCR engine used for
            scanned sources. Defaults to :data:`ocr_engine_factory`.
    """

    def __init__(
        self,
        db: Session,
        *,
        engine_factory: Callable[[], OCREngine] | None = None,
    ) -> None:
        self._db = db
        self._storage = StorageService(get_settings().upload_storage_root)
        self._applications = ApplicationRepository(db)
        self._documents = DocumentRepository(db)
        self._ocr_results = OCRRepository(db)
        self._technical = TechnicalValidationService(db)
        self._engine_factory = engine_factory or ocr_engine_factory

    def process(self, *, application_id: int) -> ProcessDocumentsResponse:
        """Run the extraction pipeline over every document of an application.

        Documents that did not pass Phase 5 technical validation are skipped,
        never processed. Each processed document's raw text and metrics are
        persisted as its OCR result; per-document failures are captured in the
        response with the document's processing status set to ``FAILED``.

        Args:
            application_id: Id of the application to process.

        Returns:
            The outcome of the run for every document.

        Raises:
            ApplicationNotFound: When the application does not exist.
            TechnicalValidationRequired: When the application has documents but
                no stored technical validation reports.
        """
        application = self._get_application(application_id)
        documents = list(
            self._documents.get_all_by_application(application_id)
        )
        reports = self._technical.get_reports(application_id=application_id)
        if documents and not reports.items:
            raise TechnicalValidationRequired()
        statuses = {
            report.document_id: report.validation_status for report in reports.items
        }
        logger.info(
            "Document processing started for application id=%s (%s documents)",
            application.id,
            len(documents),
        )
        items: list[DocumentProcessingResult] = []
        for document in documents:
            status = statuses.get(document.id)
            if status is not ValidationStatus.PASS:
                logger.warning(
                    "Skipping document id=%s (application id=%s): "
                    "did not pass technical validation",
                    document.id,
                    application.id,
                )
                items.append(
                    self._skipped_result(
                        document,
                        "Document did not pass technical validation",
                    )
                )
                continue
            items.append(self._process_document(application.id, document))

        processed = sum(item.outcome is ProcessingOutcome.PROCESSED for item in items)
        skipped = sum(item.outcome is ProcessingOutcome.SKIPPED for item in items)
        failed = sum(item.outcome is ProcessingOutcome.FAILED for item in items)
        logger.info(
            "Document processing completed for application id=%s: "
            "%s processed, %s skipped, %s failed",
            application.id,
            processed,
            skipped,
            failed,
        )
        return ProcessDocumentsResponse(
            application_id=application.id,
            items=items,
            total_processed=processed,
            total_skipped=skipped,
            total_failed=failed,
        )

    def get_results(self, *, application_id: int) -> OcrResultsResponse:
        """Return every stored OCR/text extraction result for an application.

        Args:
            application_id: Id of the application.

        Returns:
            The stored extraction results, ordered by document.

        Raises:
            ApplicationNotFound: When the application does not exist.
        """
        application = self._get_application(application_id)
        documents = {
            document.id: document
            for document in self._documents.get_all_by_application(application_id)
        }
        rows = self._ocr_results.get_by_application(application_id)
        items = [self._result_item(documents, row) for row in rows]
        logger.info(
            "Returned %s stored OCR results for application id=%s",
            len(items),
            application.id,
        )
        return OcrResultsResponse(
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

    def _process_document(
        self,
        application_id: int,
        document: Document,
    ) -> DocumentProcessingResult:
        """Extract text from one document and persist the OCR result.

        Args:
            application_id: Owning application id.
            document: Document to process.

        Returns:
            The per-document outcome, either processed or failed.
        """
        self._documents.update_status(
            document,
            DocumentProcessingStatus.PROCESSING,
        )
        started = time.perf_counter()
        deadline = time.monotonic() + PROCESSING_TIMEOUT_SECONDS
        try:
            result = self._extract(document, deadline)
            assert_non_empty_text(result.text)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._ocr_results.upsert(
                document_id=document.id,
                raw_ocr_text=result.text,
                ocr_engine=result.ocr_engine,
                processing_time_ms=elapsed_ms,
                overall_confidence=result.overall_confidence,
                processing_method=result.processing_method.value,
                page_count=result.page_count,
                character_count=result.character_count,
                processed_at=datetime.now(timezone.utc),
            )
            self._documents.update_status(
                document,
                DocumentProcessingStatus.COMPLETED,
            )
            logger.info(
                "Text extraction completed for document id=%s (application id=%s): "
                "%s characters via %s in %s ms",
                document.id,
                application_id,
                result.character_count,
                result.processing_method.value,
                elapsed_ms,
            )
            return DocumentProcessingResult(
                document_id=document.id,
                file_name=document.original_filename,
                outcome=ProcessingOutcome.PROCESSED,
                processing_method=result.processing_method,
                ocr_engine=result.ocr_engine,
                page_count=result.page_count,
                character_count=result.character_count,
                processing_time_ms=elapsed_ms,
                overall_confidence=result.overall_confidence,
                raw_text=result.text,
            )
        except DocumentProcessingError as exc:
            return self._fail_document(document, exc.detail)
        except Exception as exc:  # pragma: no cover - defensive isolation
            logger.exception(
                "Processing failed unexpectedly for document id=%s",
                document.id,
            )
            return self._fail_document(document, f"Unexpected processing error: {exc}")

    def _extract(self, document: Document, deadline: float) -> ExtractionResult:
        """Resolve, route and extract text from one document.

        Args:
            document: Document whose stored file is processed.
            deadline: Per-document processing deadline (monotonic seconds).

        Returns:
            The extraction result with text and metrics.

        Raises:
            DocumentProcessingError: When the file, format or engine fails.
        """
        path = resolve_document_file(self._storage, document.stored_file_path)
        file_format = detect_format(document.stored_file_path)
        decision = classify_document_source(path, file_format)
        logger.info(
            "Document routing decision for document id=%s: source=%s",
            document.id,
            decision.source.value,
        )
        if decision.source is DocumentSource.DIGITAL_PDF:
            extractor = DigitalPdfExtractor(decision.probed_text, decision.page_count or 0)
        elif decision.source is DocumentSource.SCANNED_PDF:
            extractor = ScannedPdfExtractor(
                self._engine_factory(),
                path,
                deadline=deadline,
            )
        else:
            extractor = ImageExtractor(self._engine_factory(), path)
        return extractor.extract()

    def _fail_document(self, document: Document, message: str) -> DocumentProcessingResult:
        """Mark a document as failed and return its failed outcome."""
        self._documents.update_status(document, DocumentProcessingStatus.FAILED)
        logger.error(
            "Processing failed for document id=%s: %s",
            document.id,
            message,
        )
        return DocumentProcessingResult(
            document_id=document.id,
            file_name=document.original_filename,
            outcome=ProcessingOutcome.FAILED,
            message=message,
        )

    def _skipped_result(self, document: Document, message: str) -> DocumentProcessingResult:
        """Build a skipped outcome without touching the document's status."""
        return DocumentProcessingResult(
            document_id=document.id,
            file_name=document.original_filename,
            outcome=ProcessingOutcome.SKIPPED,
            message=message,
        )

    def _result_item(self, documents: dict[int, Document], row: OCRResult) -> OcrResultItem:
        """Map a stored OCR result row onto its response schema.

        Args:
            documents: Application documents keyed by id.
            row: Stored OCR result.

        Returns:
            The serialized result item.
        """
        document = documents.get(row.document_id)
        return OcrResultItem(
            document_id=row.document_id,
            file_name=document.original_filename if document else "unknown",
            raw_ocr_text=row.raw_ocr_text,
            ocr_engine=row.ocr_engine,
            processing_method=row.processing_method,
            processing_time_ms=row.processing_time_ms,
            overall_confidence=row.overall_confidence,
            page_count=row.page_count,
            character_count=row.character_count,
            processed_at=row.processed_at,
        )
