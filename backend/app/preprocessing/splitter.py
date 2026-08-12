"""
Document Splitter Module.

Splits a single large PDF containing all onboarding documents into distinct
PDF files categorized by DocumentType using PyMuPDF text extraction with
PaddleOCR as a fallback for scanned/image-based pages.
"""

import io
import numpy as np
import pymupdf as fitz
from typing import BinaryIO, List, Tuple
import logging

from app.database.models.enums import DocumentType
from app.preprocessing.enhancer import ImageEnhancer

logger = logging.getLogger(__name__)

# Minimum characters from get_text() to trust it as a digital page
_MIN_TEXT_CHARS = 30


class DocumentSplitter:
    """Intelligently splits a bulk PDF into categorized individual documents."""

    _ocr_engine: "object | None" = None

    @classmethod
    def split_bulk_pdf(cls, file: BinaryIO) -> List[Tuple[DocumentType, bytes]]:
        """
        Reads a bulk PDF stream and splits it into categorized document bytes.

        For digital PDFs, uses PyMuPDF text extraction (fast).
        For scanned/image-based pages, falls back to PaddleOCR (accurate).

        Args:
            file: The binary stream of the bulk PDF.

        Returns:
            A list of tuples: (DocumentType, PDF bytes)
        """
        file_bytes = file.read()
        doc = fitz.open(stream=file_bytes, filetype="pdf")

        split_documents = []
        current_type = DocumentType.OTHER_SUPPORTING_DOCUMENT
        current_pages = []

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)

            # --- Fast path: digital PDF has extractable text ---
            text = page.get_text().strip().upper()

            # --- Slow path: scanned page → use PaddleOCR ---
            if len(text) < _MIN_TEXT_CHARS:
                text = cls._ocr_page(page)

            detected_type = cls._classify_text(text)

            if detected_type and detected_type != current_type:
                # New document boundary found — save the previous group
                if current_pages:
                    split_documents.append(
                        (current_type, cls._create_pdf(doc, current_pages))
                    )
                current_type = detected_type
                current_pages = [page_num]
            else:
                current_pages.append(page_num)

        # Save the final accumulated document
        if current_pages:
            split_documents.append(
                (current_type, cls._create_pdf(doc, current_pages))
            )

        doc.close()
        logger.info("Split bulk PDF into %d documents.", len(split_documents))
        return split_documents

    @classmethod
    def _get_ocr_engine(cls) -> object:
        """Return the shared PaddleOCR instance, creating it on first use.

        Constructing PaddleOCR downloads and loads the detection/recognition
        models, which is expensive — the engine is a process-wide singleton
        (mirrors ``document_processing.processors.PaddleOCREngine``) instead of
        being rebuilt on every OCR fallback page.
        """
        if cls._ocr_engine is None:
            from paddleocr import PaddleOCR

            cls._ocr_engine = PaddleOCR(use_angle_cls=True, lang="en", enable_mkldnn=False)
        return cls._ocr_engine

    @classmethod
    def _ocr_page(cls, page: fitz.Page) -> str:
        """
        Renders a PDF page to an image and runs PaddleOCR on it.
        Falls back to empty string if PaddleOCR is unavailable.
        """
        try:
            ocr = cls._get_ocr_engine()

            # Render page to numpy image at 150 DPI
            zoom = 150 / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.h, pix.w, pix.n
            )

            # Enhance for better OCR accuracy
            enhanced = ImageEnhancer.enhance_for_ocr(img)

            result = ocr.ocr(enhanced)
            if not result or not result[0]:
                return ""

            lines = [line[1][0] for line in result[0] if line and len(line) > 1 and line[1]]
            return " ".join(lines).upper()
        except Exception as e:
            logger.warning("OCR fallback failed for page: %s", e, exc_info=True)
            return ""

    @staticmethod
    def _classify_text(text: str) -> "DocumentType | None":
        """Heuristic keyword-based classification of document text."""
        header_text = text[:2000]

        if "TRIPARTITE AGREEMENT" in header_text:
            return DocumentType.TRIPARTITE_AGREEMENT
        if "BILATERAL AGREEMENT" in header_text or "SERVICE LEVEL AGREEMENT" in header_text:
            return DocumentType.BILATERAL_AGREEMENT
        if "ACCOUNT MAINTENANCE" in header_text:
            return DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE
        if "1LINK" in header_text or "ONE LINK" in header_text or "1-LINK" in header_text:
            return DocumentType.ONE_LINK_LETTER
        if "AUTHORITY LETTER" in header_text:
            return DocumentType.AUTHORITY_LETTER
        if "SCHEDULE OF CHARGES" in header_text:
            return DocumentType.SCHEDULE_OF_CHARGES
        if "BUSINESS REQUIREMENT" in header_text:
            return DocumentType.BUSINESS_REQUIREMENT_DOCUMENT
        if "FORMAL REQUEST" in header_text:
            return DocumentType.FORMAL_REQUEST_LETTER
        if "NATIONAL IDENTITY" in header_text or "ISLAMIC REPUBLIC OF PAKISTAN" in header_text:
            return DocumentType.CNIC_FRONT

        return None

    @staticmethod
    def _create_pdf(source_doc: fitz.Document, page_numbers: List[int]) -> bytes:
        """Extracts specific pages from a source document into a new PDF byte string."""
        new_doc = fitz.open()
        for page_num in page_numbers:
            new_doc.insert_pdf(source_doc, from_page=page_num, to_page=page_num)
        pdf_bytes = new_doc.tobytes()
        new_doc.close()
        return pdf_bytes
