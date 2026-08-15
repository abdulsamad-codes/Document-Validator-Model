"""Document Splitter Module.

Splits a single large PDF containing all onboarding documents into distinct,
conservatively classified PDF files using PyMuPDF and deterministic text
heuristics. The splitter never performs OCR, AI inference or any external call;
it only converts validated PDF bytes into logical document chunks carrying
:class:`DocumentType` metadata that the upload service persists as
queue-ready ``Document`` rows.
"""

import logging

import pymupdf as fitz

from app.database.models.enums import DocumentType
from app.upload.exceptions import (
    FileTooLargeException,
    InvalidFileTypeException,
)

logger = logging.getLogger(__name__)

#: Fraction of the page height treated as the header (title) region. Matches
#: here are *strong* boundary evidence; matches deeper in the page are treated
#: as body text and never start a document.
_HEADER_ZONE_RATIO = 0.33

#: Minimum native selectable-text characters a page must carry before it's
#: trusted as real content; below this, OCR runs instead. Scanner-app exports
#: (e.g. CamScanner) stamp a short watermark as real selectable text on every
#: page -- confirmed directly on real files in Confidential Data/: exactly
#: ``"CamScanner\n"``, 10 characters stripped. The previous threshold here was
#: a flat ``< 10``, so a watermark-only page never cleared it and OCR never
#: ran during splitting -- every page of a real scanned bulk PDF read as just
#: its watermark, matched no title phrase, and the whole file collapsed into
#: one OTHER_SUPPORTING_DOCUMENT instead of splitting. This mirrors the exact
#: same failure mode already found and fixed once before in
#: document_processing.constants.MIN_DIGITAL_TEXT_CHARS_PER_PAGE (also 40,
#: also a CamScanner watermark defeating a flat text-length bar) -- reusing
#: that already-proven value here rather than picking a new number blind.
_MIN_NATIVE_TEXT_CHARS = 40

#: Strong title phrases keyed in preference order. Iterated deterministically;
#: the first phrase found wins. These phrases are only ever treated as strong
#: evidence when anchored at the start of a line inside the header region.
_STRONG_TITLE_PHRASES: list[tuple[DocumentType, tuple[str, ...]]] = [
    (DocumentType.TRIPARTITE_AGREEMENT, ("TRIPARTITE AGREEMENT",)),
    (
        DocumentType.BILATERAL_AGREEMENT,
        ("BILATERAL AGREEMENT", "SERVICE LEVEL AGREEMENT"),
    ),
    (
        DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
        ("ACCOUNT MAINTENANCE CERTIFICATE", "ACCOUNT MAINTENANCE"),
    ),
    (
        DocumentType.ONE_LINK_LETTER,
        (
            "1LINK APPLICATION FORM",
            "1-LINK APPLICATION FORM",
            "ONE-LINK APPLICATION FORM",
            "ONE LINK APPLICATION FORM",
            "ONELINK APPLICATION FORM",
            "ONELINK",
            "ONE-LINK",
            "1LINK",
        ),
    ),
    (DocumentType.AUTHORITY_LETTER, ("AUTHORITY LETTER",)),
    (
        DocumentType.SCHEDULE_OF_CHARGES,
        (
            "SUB-BILLER AGREEMENT",
            "SUBBILER AGREEMENT",
            "SUB BILLER AGREEMENT",
            "SCHEDULE OF CHARGES",
        ),
    ),
    (
        DocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
        ("BUSINESS REQUIREMENT DOCUMENT", "BUSINESS REQUIREMENT"),
    ),
    (DocumentType.FORMAL_REQUEST_LETTER, ("FORMAL REQUEST LETTER", "FORMAL REQUEST")),
]

#: Header phrases shared by both faces of a CNIC. A page anchored with one of
#: these is a CNIC; the face is then decided by side-specific keyword scoring.
_CNIC_HEADER_PHRASES: tuple[str, ...] = (
    "COMPUTERISED NATIONAL IDENTITY",
    "COMPUTERIZED NATIONAL IDENTITY",
    "NATIONAL IDENTITY CARD",
    "ISLAMIC REPUBLIC OF PAKISTAN",
)

#: Deterministic side discriminators for the CNIC back face. Any back
#: indicator wins, so a real back page can never be labelled CNIC_FRONT.
#: ``NADRA`` is intentionally excluded: the front face also carries the NADRA
#: logo and a bare mention must not flip a front page to CNIC_BACK.
_CNIC_BACK_KEYS: tuple[str, ...] = (
    "ISSUING AUTHORITY",
    "ISSUE DATE",
    "DATE OF ISSUE",
    "PLACE OF ISSUE",
    "MANAGER",
    "THUMB",
    "QUALIFICATION",
)

#: Deterministic side discriminators for the CNIC front face.
_CNIC_FRONT_KEYS: tuple[str, ...] = (
    "IDENTITY NUMBER",
    "DATE OF BIRTH",
    "FATHER NAME",
    "FATHER'S NAME",
    "FATHERS NAME",
    "GENDER",
)


class DocumentSplitter:
    """Splits a bulk PDF into conservative, individually classified documents."""

    @classmethod
    def validate_structure(
        cls,
        content: bytes,
        *,
        max_bytes: int | None = None,
    ) -> None:
        """Cheaply reject unreadable or empty PDFs before they are queued.

        Opens the PDF just far enough to confirm it is well-formed and has at
        least one page -- no per-page classification or OCR, so this is safe
        to call synchronously from the upload request even though the actual
        split (page classification, optional OCR fallback) is deferred to the
        background queue worker.

        Raises:
            InvalidFileTypeException: When the content is empty, is not a
                readable PDF, or has zero pages.
            FileTooLargeException: When ``content`` exceeds ``max_bytes``.
        """
        if not content:
            raise InvalidFileTypeException("The uploaded file is empty")
        if max_bytes is not None and len(content) > max_bytes:
            raise FileTooLargeException(
                f"File exceeds the maximum allowed size of {max_bytes // (1024 * 1024)} MB"
            )
        if not content.startswith(b"%PDF-"):
            raise InvalidFileTypeException(
                "The uploaded file is not a valid, readable PDF"
            )

        try:
            document = fitz.open(stream=content, filetype="pdf")
        except (fitz.FileDataError, fitz.EmptyFileError, ValueError) as exc:
            raise InvalidFileTypeException(
                "The uploaded file is not a valid, readable PDF"
            ) from exc

        try:
            if len(document) == 0:
                raise InvalidFileTypeException(
                    "Bulk PDF produced no documents; expected at least one"
                )
        finally:
            document.close()

    @classmethod
    def split_bulk_pdf(
        cls,
        content: bytes,
        *,
        max_bytes: int | None = None,
        ocr_engine: object | None = None,
    ) -> list[tuple[DocumentType, bytes]]:
        """Split in-memory PDF ``content`` into categorized document bytes.

        The caller is expected to have already enforced the upload size limit;
        ``max_bytes`` is a defensive backstop so an out-of-range (e.g. future)
        call can never process a file larger than the configured maximum.

        Args:
            content: Full PDF file content (already read within the upload size
                limit — never pass a lazily-read stream here).
            max_bytes: Optional hard ceiling. Content larger than this is
                rejected with :class:`FileTooLargeException`.

        Returns:
            A list of ``(DocumentType, PDF bytes)``, one entry per logical
            document. A valid PDF that yields no logical documents is rejected.

        Raises:
            InvalidFileTypeException: When the content is empty, is not a
                readable PDF, or yields zero logical documents.
            FileTooLargeException: When ``content`` exceeds ``max_bytes``.
        """
        if not content:
            raise InvalidFileTypeException("The uploaded file is empty")
        if max_bytes is not None and len(content) > max_bytes:
            raise FileTooLargeException(
                f"File exceeds the maximum allowed size of {max_bytes // (1024 * 1024)} MB"
            )
        if not content.startswith(b"%PDF-"):
            raise InvalidFileTypeException(
                "The uploaded file is not a valid, readable PDF"
            )

        try:
            document = fitz.open(stream=content, filetype="pdf")
        except (fitz.FileDataError, fitz.EmptyFileError, ValueError) as exc:
            raise InvalidFileTypeException(
                "The uploaded file is not a valid, readable PDF"
            ) from exc

        split_documents: list[tuple[DocumentType, bytes]] = []
        current_type: DocumentType | None = None
        current_pages: list[int] = []

        try:
            for page_num in range(len(document)):
                page = document.load_page(page_num)
                detected_type, strong_evidence = cls._classify_page(page, ocr_engine)

                if strong_evidence:
                    # Strong header/title evidence marks a fresh document —
                    # even when it equals the current type (repeated copies).
                    if current_pages:
                        split_documents.append(
                            (current_type, cls._create_pdf(document, current_pages))
                        )
                    current_type = detected_type or DocumentType.OTHER_SUPPORTING_DOCUMENT
                    current_pages = [page_num]
                elif current_pages:
                    # No boundary evidence: a continuation page. Body keywords
                    # must never start a new document.
                    current_pages.append(page_num)
                else:
                    # First page without strong evidence: weak phrases only type
                    # the document; never split on them.
                    current_type = detected_type or DocumentType.OTHER_SUPPORTING_DOCUMENT
                    current_pages = [page_num]

            if current_pages:
                split_documents.append((current_type, cls._create_pdf(document, current_pages)))
        finally:
            document.close()

        if not split_documents:
            raise InvalidFileTypeException(
                "Bulk PDF produced no documents; expected at least one"
            )

        logger.info("Split bulk PDF into %s documents", len(split_documents))
        return split_documents

    @classmethod
    def _classify_page(cls, page: fitz.Page, ocr_engine: object | None = None) -> tuple[DocumentType | None, bool]:
        """Classify one page, returning ``(type, strong_evidence)``.

        ``strong_evidence`` is only ever ``True`` for anchored title phrases in
        the header region of the page. The returned type without strong
        evidence is weak/full-text evidence, usable only for typing a document
        that has no type yet.
        """
        lines = _extract_lines(page)
        page_height = page.rect.height or 0
        full_text = " ".join(text for _, text in lines)

        if len(full_text.strip()) < _MIN_NATIVE_TEXT_CHARS and ocr_engine:
            try:
                import numpy as np
                import cv2
                pix = page.get_pixmap(dpi=150)
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                if pix.n == 4:
                    img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
                
                result = ocr_engine.extract(img)
                full_text = result.text
                
                # Upper-cased to match _extract_lines' convention: every
                # phrase in _STRONG_TITLE_PHRASES/_CNIC_HEADER_PHRASES is
                # matched via a case-sensitive startswith() against an
                # all-caps phrase, so raw (non-upper-cased) OCR output would
                # silently fail to match a title printed in mixed case.
                lines = []
                for idx, line_text in enumerate(full_text.splitlines()):
                    lines.append((float(idx * 10), line_text.upper()))
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("PaddleOCR fallback failed during split: %s", exc)

        for y_position, text in lines:
            if page_height and y_position >= page_height * _HEADER_ZONE_RATIO:
                continue
            for phrase in _CNIC_HEADER_PHRASES:
                if text.startswith(phrase):
                    return cls._resolve_cnic_side(full_text), True
            for doc_type, phrases in _STRONG_TITLE_PHRASES:
                for phrase in phrases:
                    if text.startswith(phrase):
                        return doc_type, True

        return cls._classify_text(full_text), False

    @staticmethod
    def _classify_text(text: str) -> DocumentType | None:
        """Classify a page's full text with deterministic title heuristics.

        ``None`` means "no recognizable document type"; callers fall back to
        :class:`DocumentType.OTHER_SUPPORTING_DOCUMENT`.
        """
        upper = text.upper()
        for doc_type, phrases in _STRONG_TITLE_PHRASES:
            for phrase in phrases:
                if phrase in upper:
                    return doc_type
        if any(phrase in upper for phrase in _CNIC_HEADER_PHRASES):
            return DocumentSplitter._resolve_cnic_side(upper)
        return None

    @staticmethod
    def _resolve_cnic_side(full_text: str) -> DocumentType:
        """Return ``CNIC_BACK`` or ``CNIC_FRONT`` from deterministic field keys.

        Any back-side indicator wins so real back pages are never labelled
        front; otherwise front-side identity fields choose the front face. An
        unrecognised side defaults to front (the most commonly scanned face).
        """
        if any(key in full_text for key in _CNIC_BACK_KEYS):
            return DocumentType.CNIC_BACK
        if any(key in full_text for key in _CNIC_FRONT_KEYS):
            return DocumentType.CNIC_FRONT
        return DocumentType.CNIC_FRONT

    @staticmethod
    def _create_pdf(source_doc: fitz.Document, page_numbers: list[int]) -> bytes:
        """Extract specific pages from a source document into new PDF bytes."""
        new_doc = fitz.open()
        for page_num in page_numbers:
            new_doc.insert_pdf(source_doc, from_page=page_num, to_page=page_num)

        pdf_bytes = new_doc.write()
        new_doc.close()
        return pdf_bytes


def _extract_lines(page: fitz.Page) -> list[tuple[float, str]]:
    """Return ``(y0, upper-cased text)`` for every text line on the page."""
    lines: list[tuple[float, str]] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            bbox = line.get("bbox") or (0.0, 0.0, 0.0, 0.0)
            text = "".join(
                span.get("text", "") for span in line.get("spans", [])
            ).strip().upper()
            if text:
                lines.append((bbox[1], text))
    return lines