"""
Document Splitter Module.

Splits a single large PDF containing all onboarding documents into distinct
PDF files categorized by DocumentType using PyMuPDF and text heuristics.
"""

import io
import pymupdf as fitz
from typing import BinaryIO, List, Tuple
import logging

from app.database.models.enums import DocumentType

logger = logging.getLogger(__name__)


class DocumentSplitter:
    """Intelligently splits a bulk PDF into categorized individual documents."""

    @classmethod
    def split_bulk_pdf(cls, file: BinaryIO) -> List[Tuple[DocumentType, bytes]]:
        """
        Reads a bulk PDF stream and splits it into categorized document bytes.
        
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
            text = page.get_text().upper()
            
            # Identify page type based on keywords
            detected_type = cls._classify_text(text)
            
            if detected_type and detected_type != current_type:
                # We found a new document type! Save the previous one.
                if current_pages:
                    split_documents.append((current_type, cls._create_pdf(doc, current_pages)))
                current_type = detected_type
                current_pages = [page_num]
            else:
                current_pages.append(page_num)
                
        # Save the final accumulated document
        if current_pages:
            split_documents.append((current_type, cls._create_pdf(doc, current_pages)))
            
        doc.close()
        
        logger.info(f"Split bulk PDF into {len(split_documents)} documents.")
        return split_documents

    @staticmethod
    def _classify_text(text: str) -> DocumentType | None:
        """Heuristic-based classification of document text."""
        # Check first 1500 characters for headers
        header_text = text[:1500]
        
        if "TRIPARTITE AGREEMENT" in header_text:
            return DocumentType.TRIPARTITE_AGREEMENT
        if "BILATERAL AGREEMENT" in header_text or "SERVICE LEVEL AGREEMENT" in header_text:
            return DocumentType.BILATERAL_AGREEMENT
        if "ACCOUNT MAINTENANCE" in header_text:
            return DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE
        if "1LINK" in header_text or "ONE LINK" in header_text:
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
            
        pdf_bytes = new_doc.write()
        new_doc.close()
        return pdf_bytes
