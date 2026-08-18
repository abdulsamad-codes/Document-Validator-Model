"""Unit tests for the DocumentSplitter module.

Tests that bulk PDFs are classified into logical document chunks. These tests
are fully self-contained and require no database.
"""

import io

import pymupdf
import pytest

from app.database.models.enums import DocumentType
from app.preprocessing.splitter import DocumentSplitter
from app.upload.exceptions import FileTooLargeException, InvalidFileTypeException


def _make_pdf_with_text(pages: list[str]) -> bytes:
    """Create a minimal in-memory PDF with one text page per item."""
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((50, 50), text, fontsize=14)
    buffer = io.BytesIO(doc.tobytes())
    doc.close()
    return buffer.getvalue()


def _split(page_texts: list[str]) -> list[tuple[DocumentType, bytes]]:
    return DocumentSplitter.split_bulk_pdf(_make_pdf_with_text(page_texts))


def _doc_types(page_texts: list[str]) -> list[DocumentType]:
    return [doc_type for doc_type, _ in _split(page_texts)]


# --- Classification ---------------------------------------------------------


def test_split_single_known_document():
    """A PDF with a clear header should return one categorized document."""
    result = _split(["TRIPARTITE AGREEMENT\nThis is an agreement."])
    assert len(result) == 1
    assert result[0][0] == DocumentType.TRIPARTITE_AGREEMENT


def test_split_multiple_known_documents():
    """A PDF with multiple distinct headers should yield multiple documents."""
    types = _doc_types([
        "TRIPARTITE AGREEMENT\nContent here.",
        "AUTHORITY LETTER\nContent here.",
        "ACCOUNT MAINTENANCE CERTIFICATE\nContent here.",
    ])
    assert types == [
        DocumentType.TRIPARTITE_AGREEMENT,
        DocumentType.AUTHORITY_LETTER,
        DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    ]


def test_split_unclassified_pages_become_other():
    """Pages with no matching keywords should be grouped as OTHER_SUPPORTING_DOCUMENT."""
    result = _split(["Random unrecognized document content."])
    assert len(result) == 1
    assert result[0][0] == DocumentType.OTHER_SUPPORTING_DOCUMENT


def test_split_repeated_same_type_copies():
    """Repeated copies of the same type must each become their own document."""
    types = _doc_types([
        "TRIPARTITE AGREEMENT\nCopy one body.",
        "TRIPARTITE AGREEMENT\nCopy two body.",
        "TRIPARTITE AGREEMENT\nCopy three body.",
    ])
    assert [t for t in types if t == DocumentType.TRIPARTITE_AGREEMENT] == [
        DocumentType.TRIPARTITE_AGREEMENT,
        DocumentType.TRIPARTITE_AGREEMENT,
        DocumentType.TRIPARTITE_AGREEMENT,
    ]


def test_split_mixed_repeated_copies_and_pairs():
    """Multiple copies of 1-Link, Schedule of Charges and a CNIC pair."""
    types = _doc_types([
        "1LINK APPLICATION FORM\nFirst copy.",
        "1LINK APPLICATION FORM\nSecond copy.",
        "1LINK APPLICATION FORM\nThird copy.",
        "SCHEDULE OF CHARGES\nSix copies include this one.",
        "SCHEDULE OF CHARGES\nAnother.",
        "NATIONAL IDENTITY CARD\nIdentity Number: 42101-0000000-0\nFather Name: Ali",
        "ISLAMIC REPUBLIC OF PAKISTAN\nDate of Issue: 01-01-2010\nIssuing Authority: NADRA",
    ])
    assert types.count(DocumentType.ONE_LINK_LETTER) == 3
    assert types.count(DocumentType.SCHEDULE_OF_CHARGES) == 2
    assert types.count(DocumentType.CNIC_FRONT) == 1
    assert types.count(DocumentType.CNIC_BACK) == 1
    assert DocumentType.CNIC_BACK in types


def test_split_cnic_back_is_not_front():
    """A back face with issuing-authority fields must be CNIC_BACK, not FRONT."""
    types = _doc_types([
        "NATIONAL IDENTITY CARD\nIdentity Number: 42101-0000000-0\nFather Name: Ali",
        "NATIONAL IDENTITY CARD\nDate of Issue: 01-01-2010\nIssuing Authority: NADRA",
    ])
    assert types == [DocumentType.CNIC_FRONT, DocumentType.CNIC_BACK]


def test_split_continuation_page_does_not_split():
    """Body keywords on a continuation page must not start a new document."""
    types = _doc_types([
        "TRIPARTITE AGREEMENT\nPage 1.",
        "as per the 1LINK tripartite agreement and schedule of charges on page 2.",
        "continued agreement text on page 3.",
    ])
    assert types == [DocumentType.TRIPARTITE_AGREEMENT]


def test_split_consecutive_same_type_grouped():
    """A title page plus unclassified continuation pages stay one document."""
    result = _split([
        "SCHEDULE OF CHARGES\nPage 1.",
        "Continuation of the schedule on page 2.",
    ])
    assert len(result) == 1
    assert result[0][0] == DocumentType.SCHEDULE_OF_CHARGES


def test_split_checklist_cover_page_is_not_misclassified():
    """A checklist page listing required documents by name must not be
    mistaken for one of the documents it lists.

    Regression test for a real bug found 2026-08-16 on a real file in
    Confidential Data/: a checklist/manifest cover page's first table row
    ("Authority Letter of officer - Signed") fell inside the header zone and
    strong-matched AUTHORITY_LETTER, producing a spurious second copy of a
    document that only existed once for real -- confirmed by comparing the
    real page's actual OCR text (a checklist titled "CHECKLIST FOR
    ON-BOARDING...") against the real single genuine Authority Letter page
    later in the same file.
    """
    types = _doc_types([
        "CHECKLIST\nAuthority Letter of officer - Signed\n"
        "Account Maintenance Certificate from Bank",
        "AUTHORITY LETTER\nIt is hereby authorized that the officer may act "
        "on our behalf.",
    ])
    assert types == [
        DocumentType.OTHER_SUPPORTING_DOCUMENT,
        DocumentType.AUTHORITY_LETTER,
    ]


def test_split_master_checklist_cover_page_is_not_misclassified():
    """A "MASTER CHECKLIST" cover page must also be excluded, not just plain
    "CHECKLIST".

    Regression test for a second real file found 2026-08-16 with the exact
    same underlying bug but a different checklist title: a prefix
    (startswith) check on "CHECKLIST" caught a real file titled plain
    "CHECKLIST" but silently missed this real file's "MASTER CHECKLIST",
    whose own "Authority Letter" table row (this time with no trailing
    text) again strong-matched AUTHORITY_LETTER.
    """
    types = _doc_types([
        "MASTER CHECKLIST\nAuthority Letter\nAccount Maintenance Certificate",
        "AUTHORITY LETTER\nIt is hereby authorized that the officer may act "
        "on our behalf.",
    ])
    assert types == [
        DocumentType.OTHER_SUPPORTING_DOCUMENT,
        DocumentType.AUTHORITY_LETTER,
    ]


def test_split_genuine_application_form_title_is_one_link_letter():
    """The genuine 1-Link Application Form's own real title must start a new
    document, not be silently absorbed as an untyped continuation.

    Regression test for a real bug found 2026-08-18 on TMA Lal Dir Upper.pdf
    (Confidential Data/): docs/Master_Rules_Combined.md Section 4's real
    Application Form starts its own page with "Application Form (In-Direct
    Customer)" -- it never carries a "1LINK"/"ONE-LINK"/"ONELINK" brand
    prefix on the page itself, so none of the existing ONE_LINK_LETTER
    phrases (all brand-prefixed) ever matched it; the page was silently
    absorbed as a continuation of whichever unrelated document preceded it
    instead. The same real title, previously unidentified, was also found
    hiding in 3 other already-cached real samples from 2 other files.
    """
    types = _doc_types([
        "AUTHORITY LETTER\nUnrelated preceding document body.",
        "Application Form (In-Direct Customer)\nKnow Your Customer, Form A.",
    ])
    assert types == [DocumentType.AUTHORITY_LETTER, DocumentType.ONE_LINK_LETTER]


def test_split_application_form_repeated_pages_become_separate_copies():
    """A known, accepted side effect of the fix above: since the real
    Application Form repeats its own title on every one of its pages (Form
    A, the directors continuation, Form B), each page independently strong-
    matches and starts its own document -- 3 separate ONE_LINK_LETTER copies,
    not one merged 3-page document. Documented, not silently assumed: this
    matches upload/constants.py::MAX_COPIES_BY_DOCUMENT_TYPE already
    allowing up to 3 copies of this type, and mirrors the same per-page
    strong-match behavior already covered by
    test_split_repeated_same_type_copies for other types.
    """
    types = _doc_types([
        "Application Form (In-Direct Customer)\nForm A, company details.",
        "Application Form (In-Direct Customer)\nDirectors/partners table.",
        "Application Form (In-Direct Customer)\nForm B, business information.",
    ])
    assert types == [
        DocumentType.ONE_LINK_LETTER,
        DocumentType.ONE_LINK_LETTER,
        DocumentType.ONE_LINK_LETTER,
    ]


def test_classify_text_authority_letter():
    """The classifier should detect AUTHORITY LETTER keyword."""
    doc_type = DocumentSplitter._classify_text("AUTHORITY LETTER\nFrom the CEO")
    assert doc_type == DocumentType.AUTHORITY_LETTER


def test_classify_text_none_for_unrecognized():
    """The classifier should return None for unrecognized text."""
    assert DocumentSplitter._classify_text("Random text with no match.") is None


# --- Validation / error handling -------------------------------------------


def test_split_empty_pdf_rejected():
    """An empty PDF must be rejected with an UploadError, not returned as []."""
    with pytest.raises(InvalidFileTypeException):
        DocumentSplitter.split_bulk_pdf(b"")


def test_split_zero_page_pdf_rejected():
    """A valid PDF with no pages must be rejected (no logical documents)."""
    zero_page_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Count 0 /Kids [] >>\nendobj\n"
        b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
    )
    with pytest.raises(InvalidFileTypeException) as excinfo:
        DocumentSplitter.split_bulk_pdf(zero_page_pdf)
    assert "no documents" in excinfo.value.detail.lower()


def test_split_truncated_pdf_rejected():
    """A truncated PDF (valid header, corrupt body) must map to a 400 error."""
    with pytest.raises(InvalidFileTypeException):
        DocumentSplitter.split_bulk_pdf(b"%PDF-1.4\n%%EOF")


def test_split_non_pdf_bytes_rejected():
    """Garbage bytes that are not a PDF must map to a 400 error."""
    with pytest.raises(InvalidFileTypeException):
        DocumentSplitter.split_bulk_pdf(b"\xff\xd8\xff\xe0\x00\x10JFIF not a pdf")


def test_split_oversized_rejected():
    """Content over the enforced ceiling must raise FileTooLargeException."""
    content = _make_pdf_with_text(["TRIPARTITE AGREEMENT\nBody."])
    with pytest.raises(FileTooLargeException):
        DocumentSplitter.split_bulk_pdf(content, max_bytes=len(content) - 1)


# --- Output integrity ------------------------------------------------------


def test_split_output_is_valid_pdf():
    """Every split chunk must be a readable single-page PDF."""
    result = _split(["AUTHORITY LETTER\nBody.", "BILATERAL AGREEMENT\nBody."])
    assert len(result) == 2
    for doc_type, pdf_bytes in result:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            assert len(doc) == 1
        assert doc_type in (DocumentType.AUTHORITY_LETTER, DocumentType.BILATERAL_AGREEMENT)