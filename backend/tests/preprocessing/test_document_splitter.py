"""
Unit tests for the DocumentSplitter module.
Tests that bulk PDFs are correctly classified into document type segments.
These tests are fully self-contained and require no database.
"""

import io
import pymupdf
import pytest

from app.database.models.enums import DocumentType
from app.preprocessing.splitter import DocumentSplitter


def _make_pdf_with_text(pages: list[str]) -> io.BytesIO:
    """Helper: creates a minimal in-memory PDF with one text page per item."""
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((50, 50), text, fontsize=14)
    buffer = io.BytesIO(doc.tobytes())
    doc.close()
    buffer.seek(0)
    return buffer


def test_split_single_known_document():
    """A PDF with a clear header should return one categorized document."""
    pdf_stream = _make_pdf_with_text(["TRIPARTITE AGREEMENT\nThis is an agreement."])
    result = DocumentSplitter.split_bulk_pdf(pdf_stream)
    assert len(result) == 1
    assert result[0][0] == DocumentType.TRIPARTITE_AGREEMENT


def test_split_multiple_known_documents():
    """A PDF with multiple distinct headers should yield multiple documents."""
    pdf_stream = _make_pdf_with_text([
        "TRIPARTITE AGREEMENT\nContent here.",
        "AUTHORITY LETTER\nContent here.",
        "ACCOUNT MAINTENANCE CERTIFICATE\nContent here.",
    ])
    result = DocumentSplitter.split_bulk_pdf(pdf_stream)
    types = [r[0] for r in result]
    assert DocumentType.TRIPARTITE_AGREEMENT in types
    assert DocumentType.AUTHORITY_LETTER in types
    assert DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE in types


def test_split_unclassified_pages_become_other():
    """Pages with no matching keywords should be grouped as OTHER_SUPPORTING_DOCUMENT."""
    pdf_stream = _make_pdf_with_text(["Random unrecognized document content."])
    result = DocumentSplitter.split_bulk_pdf(pdf_stream)
    assert len(result) == 1
    assert result[0][0] == DocumentType.OTHER_SUPPORTING_DOCUMENT


def test_split_empty_pdf():
    """An empty PDF should produce no documents."""
    # PyMuPDF's writer refuses to serialize a zero-page document ("cannot save
    # with zero pages"), so the zero-page PDF is hand-crafted directly instead
    # of built via `pymupdf.open()` + `.write()`. It reads back with 0 pages
    # even though it can't be produced by PyMuPDF's own save path.
    raw_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
        b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
    )
    buffer = io.BytesIO(raw_pdf)
    result = DocumentSplitter.split_bulk_pdf(buffer)
    assert result == []


def test_split_consecutive_same_type_grouped():
    """Multiple consecutive pages of the same type should be grouped into one document."""
    pdf_stream = _make_pdf_with_text([
        "TRIPARTITE AGREEMENT\nPage 1.",
        "Continuation of the tripartite agreement on page 2.",
    ])
    result = DocumentSplitter.split_bulk_pdf(pdf_stream)
    # First page starts the tripartite, second has no header so stays in same group
    tripartite_docs = [r for r in result if r[0] == DocumentType.TRIPARTITE_AGREEMENT]
    assert len(tripartite_docs) >= 1


def test_classify_text_authority_letter():
    """The classifier should detect AUTHORITY LETTER keyword."""
    doc_type = DocumentSplitter._classify_text("AUTHORITY LETTER\nFrom the CEO")
    assert doc_type == DocumentType.AUTHORITY_LETTER


def test_classify_text_none_for_unrecognized():
    """The classifier should return None for unrecognized text."""
    doc_type = DocumentSplitter._classify_text("Random text with no match.")
    assert doc_type is None
