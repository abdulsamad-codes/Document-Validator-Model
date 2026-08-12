"""Upload service: orchestrates validation, storage and persistence.

Keeps the route layer thin: routes parse and document HTTP concerns, the service
implements the actual upload workflow (validate -> store -> persist metadata),
replacement, deletion and retrieval. Every public method is a self-contained
transaction that raises the module's domain exceptions, which the route layer
converts into HTTP responses.
"""

import logging
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models.application import Application
from app.database.models.document import Document
from app.database.models.enums import ApplicationStatus, DocumentProcessingStatus, DocumentType
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_repository import DocumentRepository
from app.upload.constants import MAX_COPIES_BY_DOCUMENT_TYPE, READ_CHUNK_BYTES
from app.upload.exceptions import (
    ApplicationNotFoundException,
    DocumentNotFoundException,
    DuplicateDocumentException,
    FileTooLargeException,
    InvalidFileTypeException,
    StorageException,
)
from app.upload.storage import StorageService
from app.upload.validators import sanitize_filename, validate_file_content

logger = logging.getLogger(__name__)


class UploadService:
    """Implements the document upload and management workflows.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._storage = StorageService(get_settings().upload_storage_root)
        self._applications = ApplicationRepository(db)
        self._documents = DocumentRepository(db)
        self._max_bytes = get_settings().max_upload_size_mb * 1024 * 1024

    def create_application(
        self,
        *,
        created_by: str,
        notes: str | None = None,
    ) -> Application:
        """Create a new application to own uploaded documents.

        Args:
            created_by: Identifier of the submitting user.
            notes: Optional free-form notes.

        Returns:
            The persisted application.
        """
        application = self._applications.create(created_by=created_by, notes=notes)
        logger.info("Created application id=%s by %r", application.id, created_by)
        return application

    def list_applications(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        status: ApplicationStatus | None = None,
    ) -> tuple[list[Application], int]:
        """List applications, optionally filtered by status.

        Args:
            offset: Number of applications to skip.
            limit: Maximum number of applications to return.
            status: When given, only return applications in this status.

        Returns:
            A tuple of ``(applications, total)`` where ``total`` is the
            unpaginated count for the current filter.
        """
        applications = self._applications.list(offset=offset, limit=limit, status=status)
        statement = select(func.count()).select_from(Application)
        if status is not None:
            statement = statement.where(Application.status == status)
        total = self._db.scalar(statement) or 0
        logger.info("Listed %s applications (total=%s)", len(applications), total)
        return list(applications), total

    def get_application(self, application_id: int) -> Application:
        """Return an application or raise ``ApplicationNotFoundException``.

        Args:
            application_id: Id of the application to fetch.

        Returns:
            The matching application.
        """
        return self._get_application(application_id)

    def upload(
        self,
        *,
        application_id: int,
        document_type: DocumentType,
        filename: str,
        content_type: str,
        file: BinaryIO,
        copy_number: int = 1,
    ) -> Document:
        """Validate and persist a newly uploaded document.

        Args:
            application_id: Id of the owning application.
            document_type: Category of the document.
            filename: Raw client-supplied filename.
            content_type: Declared media type.
            file: Stream to read the file content from.
            copy_number: 1-based slot index for this copy within the type,
                e.g. ``3`` for the third 1-Link form.

        Returns:
            The persisted document metadata with ``UPLOADED`` status.

        Raises:
            ApplicationNotFoundException: When the application does not exist.
            DuplicateDocumentException: When the application already holds the
                maximum number of documents of this type, or when the requested
                copy slot is already occupied.
            MissingFileException / InvalidFileTypeException /
                FileTooLargeException: When the file fails validation.
        """
        application = self._get_application(application_id)
        self._ensure_slot_available(application_id, document_type, copy_number)

        content = self._read_with_limit(file)
        extension = validate_file_content(filename, content_type, content)
        safe_filename = sanitize_filename(filename)

        stored_path = self._storage.save(application.id, document_type, content, extension)
        try:
            document = self._documents.create(
                application_id=application.id,
                document_type=document_type,
                copy_number=copy_number,
                original_filename=safe_filename,
                stored_file_path=stored_path,
                file_type=_content_type_for(extension),
                processing_status=DocumentProcessingStatus.UPLOADED,
            )
        except Exception:
            # Roll back the persisted metadata and clean up the orphaned file.
            self._db.rollback()
            self._storage.delete(stored_path)
            raise

        logger.info(
            "Uploaded document id=%s type=%s copy=%s for application id=%s stored=%s",
            document.id,
            document_type.value,
            copy_number,
            application.id,
            stored_path,
        )
        return document

    def upload_bulk(
        self,
        *,
        application_id: int,
        filename: str,
        content_type: str,
        file: BinaryIO,
    ) -> list[Document]:
        """Accept a single bulk PDF, split it into individual documents, and persist each.

        Uses the DocumentSplitter to detect document boundaries using text
        heuristics (PyMuPDF `get_text`), then persists each split sub-document
        with its detected DocumentType.

        Args:
            application_id: Id of the owning application.
            filename: Raw client-supplied filename.
            content_type: Declared media type (must be PDF).
            file: Stream of the bulk PDF.

        Returns:
            A list of persisted Document records, one per detected document type.

        Raises:
            ApplicationNotFoundException: When the application does not exist.
            InvalidFileTypeException: When the file is not a PDF.
        """
        from app.preprocessing.splitter import DocumentSplitter

        application = self._get_application(application_id)

        # Validate that it's a PDF before we try to split it
        validate_file_content(filename, content_type, file.read(8))
        file.seek(0)

        split_results = DocumentSplitter.split_bulk_pdf(file)
        created_documents: list[Document] = []

        logger.info(
            "Bulk upload for application id=%s: splitting %s into %d documents",
            application_id,
            filename,
            len(split_results),
        )

        for doc_type, pdf_bytes in split_results:
            # Track copy numbers per type for multi-copy document types
            existing_copies = sum(
                1 for d in created_documents if d.document_type == doc_type
            )
            copy_number = existing_copies + 1

            stored_path = self._storage.save(
                application.id, doc_type, pdf_bytes, ".pdf"
            )
            try:
                document = self._documents.create(
                    application_id=application.id,
                    document_type=doc_type,
                    copy_number=copy_number,
                    original_filename=f"{doc_type.value.lower()}_copy{copy_number}.pdf",
                    stored_file_path=stored_path,
                    file_type="application/pdf",
                    processing_status=DocumentProcessingStatus.UPLOADED,
                )
                created_documents.append(document)
            except Exception:
                self._db.rollback()
                self._storage.delete(stored_path)
                raise

        logger.info(
            "Bulk upload complete: created %d documents for application id=%s",
            len(created_documents),
            application_id,
        )
        return created_documents

    def replace(
        self,
        *,
        application_id: int,
        document_id: int,
        document_type: DocumentType,
        filename: str,
        content_type: str,
        file: BinaryIO,
    ) -> Document:
        """Replace an existing document's file and metadata.

        The new file is persisted first; only after the database row is updated
        is the previous file removed, so a failure never loses the old version.

        Args:
            application_id: Id of the owning application.
            document_id: Id of the document to replace.
            document_type: Category for the replacement document.
            filename: Raw client-supplied filename.
            content_type: Declared media type.
            file: Stream to read the new file content from.

        Returns:
            The updated document metadata.

        Raises:
            ApplicationNotFoundException: When the application does not exist.
            DocumentNotFoundException: When the document does not exist or does
                not belong to the application.
            MissingFileException / InvalidFileTypeException /
                FileTooLargeException: When the new file fails validation.
        """
        self._get_application(application_id)
        document = self._get_document_for_application(application_id, document_id)
        previous_path = document.stored_file_path

        content = self._read_with_limit(file)
        extension = validate_file_content(filename, content_type, content)
        safe_filename = sanitize_filename(filename)

        new_path = self._storage.save(application_id, document_type, content, extension)
        try:
            document.document_type = document_type
            document.original_filename = safe_filename
            document.file_type = _content_type_for(extension)
            document.stored_file_path = new_path
            document.processing_status = DocumentProcessingStatus.UPLOADED
            self._db.add(document)
            self._db.commit()
            self._db.refresh(document)
        except Exception:
            self._db.rollback()
            self._storage.delete(new_path)
            raise

        self._delete_file(previous_path)
        logger.info(
            "Replaced document id=%s (application id=%s) stored=%s",
            document.id,
            application_id,
            new_path,
        )
        return document

    def delete(self, *, application_id: int, document_id: int) -> None:
        """Delete a document's metadata and its stored file.

        Args:
            application_id: Id of the owning application.
            document_id: Id of the document to delete.

        Raises:
            ApplicationNotFoundException: When the application does not exist.
            DocumentNotFoundException: When the document does not exist or does
                not belong to the application.
        """
        self._get_application(application_id)
        document = self._get_document_for_application(application_id, document_id)
        stored_path = document.stored_file_path

        self._documents.delete(document)
        self._delete_file(stored_path)
        logger.info(
            "Deleted document id=%s (application id=%s)",
            document_id,
            application_id,
        )

    def list_documents(
        self,
        *,
        application_id: int,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Document], int]:
        """Return an application's documents ordered by upload time.

        Args:
            application_id: Id of the owning application.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A tuple of ``(documents, total)`` where ``total`` ignores pagination.

        Raises:
            ApplicationNotFoundException: When the application does not exist.
        """
        self._get_application(application_id)
        documents = list(
            self._documents.get_by_application(application_id, offset=offset, limit=limit)
        )
        total = self._db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.application_id == application_id)
        )
        return documents, int(total or 0)

    def get_document(self, *, document_id: int) -> Document:
        """Return a single document's metadata.

        Args:
            document_id: Id of the document.

        Returns:
            The matching document.

        Raises:
            DocumentNotFoundException: When the document does not exist.
        """
        document = self._documents.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundException()
        return document

    def download(self, *, document_id: int) -> tuple[Document, Path]:
        """Resolve a document's stored file for download.

        Args:
            document_id: Id of the document.

        Returns:
            A tuple of ``(document, absolute_file_path)`` so the caller can
            stream the file with the document's media type and original name.

        Raises:
            DocumentNotFoundException: When the document does not exist.
        """
        document = self.get_document(document_id=document_id)
        path = self._storage.resolve(document.stored_file_path)
        logger.info(
            "Download requested for document id=%s (application id=%s)",
            document.id,
            document.application_id,
        )
        return document, path

    def _get_application(self, application_id: int) -> Application:
        """Return an application or raise ``ApplicationNotFoundException``."""
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFoundException()
        return application

    def _get_document_for_application(
        self,
        application_id: int,
        document_id: int,
    ) -> Document:
        """Return a document owned by the application, or raise a 404."""
        document = self._documents.get_by_id(document_id)
        if document is None or document.application_id != application_id:
            raise DocumentNotFoundException()
        return document

    def _ensure_slot_available(
        self,
        application_id: int,
        document_type: DocumentType,
        copy_number: int,
    ) -> None:
        """Raise ``DuplicateDocumentException`` when the copy slot is unavailable.

        A type is limited to ``MAX_COPIES_BY_DOCUMENT_TYPE`` copies per
        application; types outside the map accept a single copy. Within the
        limit, each 1-based copy number is a distinct, stable slot so a copy
        can never silently overwrite a sibling of the same type.
        """
        max_copies = MAX_COPIES_BY_DOCUMENT_TYPE.get(document_type, 1)
        if copy_number < 1 or copy_number > max_copies:
            noun = "copy" if max_copies == 1 else "copies"
            raise DuplicateDocumentException(
                f"Cannot upload more than {max_copies} {noun} of "
                f"{document_type.value} per application"
            )

        statement = select(Document).where(
            Document.application_id == application_id,
            Document.document_type == document_type,
            Document.copy_number == copy_number,
        )
        if self._db.scalar(statement) is not None:
            raise DuplicateDocumentException(
                f"Copy {copy_number} of {document_type.value} already exists for this application"
            )

    def _read_with_limit(self, file: BinaryIO) -> bytes:
        """Stream the file, enforcing the configured maximum size.

        Args:
            file: Stream to read from.

        Returns:
            The complete file content, or ``b""`` for an empty file (empty
            content is rejected later during content validation).

        Raises:
            FileTooLargeException: When the content exceeds the size limit.
        """
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = file.read(READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > self._max_bytes:
                raise FileTooLargeException(
                    f"File exceeds the maximum allowed size of "
                    f"{self._max_bytes // (1024 * 1024)} MB"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    def _delete_file(self, stored_file_path: str) -> None:
        """Remove a stored file, logging but swallowing storage errors.

        A failure here must not fail the request after the database has already
        committed; the orphaned file is reported through the logs instead.
        """
        try:
            self._storage.delete(stored_file_path)
        except StorageException:
            logger.exception(
                "Could not remove stored file %r; manual cleanup required",
                stored_file_path,
            )


def _content_type_for(extension: str) -> str:
    """Return the canonical media type for a validated extension."""
    from app.upload.constants import MIME_TYPES_BY_EXTENSION

    types = MIME_TYPES_BY_EXTENSION.get(extension)
    return next(iter(types)) if types else "application/octet-stream"
