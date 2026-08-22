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
    return DocumentSplitter.split_bulk_pdf(_make_pdf_with_text(page_texts)).documents


def _split_full(page_texts: list[str]):
    """Return the full ``SplitResult`` (documents + absorption warnings)."""
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


def test_split_application_form_three_pages_group_into_one_document():
    """Corrects a wrong assumption from an earlier pass of this fix: the
    real Application Form's page count is NOT fixed at 3 -- checked against
    4 real cached samples 2026-08-18, 3 files show 3 pages, a 4th
    (GDA Abbotabad) shows 4. The form's own title repeats on every one of
    its pages regardless of count, so each page independently strong-
    matching used to produce N separate ONE_LINK_LETTER copies instead of
    one logical document -- silently over-fragmenting the real form and, in
    at least one real file, pushing the type past
    MAX_COPIES_BY_DOCUMENT_TYPE's cap of 3 and hard-failing the entire bulk
    upload (found the same day, TMA Khal Dir Lower.pdf: 3 form pages + 1
    pre-existing genuine ONE_LINK_LETTER sample = 4, over the cap).

    Fixed by _CONTINUATION_TITLE_PHRASES: a repeat of this exact phrase on
    the immediately following strong-matched page extends the current
    document instead of starting a new one. This is the 3-page case.
    """
    types = _doc_types([
        "Application Form (In-Direct Customer)\nForm A, company details.",
        "Application Form (In-Direct Customer)\nDirectors/partners table.",
        "Application Form (In-Direct Customer)\nForm B, business information.",
    ])
    assert types == [DocumentType.ONE_LINK_LETTER]


def test_split_application_form_four_pages_group_into_one_document():
    """Same fix, the 4-page case -- confirmed page-count-agnostic, not
    hardcoded to 3. Matches the real GDA Abbotabad.pdf sample's own shape
    (an extra page beyond the other 3 samples' 3-page structure).
    """
    types = _doc_types([
        "Application Form (In-Direct Customer)\nForm A, company details.",
        "Application Form (In-Direct Customer)\nDirectors/partners table.",
        "Application Form (In-Direct Customer)\nLicense status table.",
        "Application Form (In-Direct Customer)\nForm B, business information.",
    ])
    assert types == [DocumentType.ONE_LINK_LETTER]


def test_split_application_form_ends_before_a_genuinely_different_document():
    """The grouping above must stop cleanly once the repeating phrase
    stops, so a real, different document immediately following the form
    still starts its own document rather than being absorbed into it.
    """
    types = _doc_types([
        "Application Form (In-Direct Customer)\nForm A, company details.",
        "Application Form (In-Direct Customer)\nForm B, business information.",
        "AUTHORITY LETTER\nA separate, unrelated document right after.",
    ])
    assert types == [DocumentType.ONE_LINK_LETTER, DocumentType.AUTHORITY_LETTER]


def test_split_application_form_matches_despite_ocr_misread_of_last_word():
    """Real GDC Alpurai Shangla.pdf OCR's this title as "...Customex)" (a
    one-character misread of "Customer)") -- confirmed 2026-08-22 by
    reading the real cached OCR text directly. The exact-string match that
    fixed the other 3 real samples of this same title did not catch this
    one; the phrase was narrowed to a prefix (drops the last word) so any
    misread of it doesn't matter.
    """
    types = _doc_types([
        "AUTHORITY LETTER\nUnrelated preceding document.",
        "Application Form (In-Direct Customex)\nForm A, company details.",
    ])
    assert types == [DocumentType.AUTHORITY_LETTER, DocumentType.ONE_LINK_LETTER]


def test_split_application_form_ocr_misread_still_groups_multipage():
    """The prefix match must still support the multi-page continuation
    grouping (_CONTINUATION_TITLE_PHRASES) even when the repeated title is
    OCR-misread the same way on every page, matching GDC Alpurai Shangla's
    real 2-of-3 pages carrying the identical "...Customex)" misread.
    """
    types = _doc_types([
        "Application Form (In-Direct Customex)\nForm A, company details.",
        "Application Form (In-Direct Customex)\nDirectors/partners table.",
        "Application Form (In-Direct Customer)\nForm B, business information.",
    ])
    assert types == [DocumentType.ONE_LINK_LETTER]


def _stamp_paper_boilerplate(lines: int = 30) -> str:
    """Simulate the fixed verification/QR boilerplate block real e-stamp
    paper pages carry before their actual title -- see
    _FULL_PAGE_STRONG_PHRASES's docstring. 30 lines reliably pushes real
    rendered text past a real PDF page's header-zone cutoff (confirmed
    empirically: ~451pt vs. the ~278pt cutoff on an A4-sized page).
    """
    return "\n".join(f"Stamp paper boilerplate line {i}" for i in range(lines))


def test_split_participation_memorandum_starts_own_group_past_boilerplate():
    """A real Participation Memorandum's title sits well below the header
    zone, after a fixed stamp-paper boilerplate block -- it must still
    start its own new document (not be absorbed into a preceding,
    unrelated open group) and must be typed ONE_LINK_LETTER, not
    OTHER_SUPPORTING_DOCUMENT or misclassified via the bare "1LINK"
    mentions in its own body text.

    Regression test for a real bug found 2026-08-18 across 3 real samples
    (GDA Abbotabad, TMA Khal Dir Lower): this title was previously invisible
    to the splitter entirely (absent from _STRONG_TITLE_PHRASES) and, once
    a group happened to be open, silently absorbed into whatever document
    preceded it -- or, if no group was open, mistyped as ONE_LINK_LETTER
    via the bare "1LINK" weak substring match rather than genuinely
    recognized.
    """
    body = (
        _stamp_paper_boilerplate()
        + "\nPARTICIPATION MEMORANDUM FOR BILLER/SUB-BILLERS/BILL AGGREGATOR MEMBERS\n"
        + "This Participation Memorandum is supplemental to the Agreement "
        + "executed between 1LINK (Private) Limited and the Bill Aggregator."
    )
    types = _doc_types([
        "AUTHORITY LETTER\nAn unrelated, genuinely different document first.",
        body,
    ])
    assert types == [DocumentType.AUTHORITY_LETTER, DocumentType.ONE_LINK_LETTER]


def test_split_bare_1link_mention_no_longer_weakly_misclassifies():
    """A page that merely *mentions* "1LINK" in prose, with no strong title
    evidence anywhere, must not be weakly typed ONE_LINK_LETTER anymore --
    it should fall through to OTHER_SUPPORTING_DOCUMENT like any other
    unrecognized page.

    Regression test for the narrowed weak-match: real Participation
    Memorandum documents mention "1LINK" throughout their own body (1LINK
    is the counterparty they're addressed to, not the document's subject),
    which previously caused _classify_text's unanchored substring check to
    mistype unrelated pages as ONE_LINK_LETTER. See
    _WEAK_MATCH_EXCLUDED_PHRASES.
    """
    types = _doc_types([
        "This memo references 1LINK services and ONELINK settlement rules "
        "in passing, but is not itself a 1-Link document of any kind.",
    ])
    assert types == [DocumentType.OTHER_SUPPORTING_DOCUMENT]


def test_split_bare_1link_still_strong_matches_as_its_own_header():
    """The narrowing only removes the bare brand phrases from *weak*
    whole-page matching -- a page whose own header-zone line genuinely
    starts with just "1LINK" (a real letterhead/logo shape) must still be
    recognized as strong evidence, unchanged.
    """
    types = _doc_types([
        "1LINK\nA genuine letterhead-only title page.",
    ])
    assert types == [DocumentType.ONE_LINK_LETTER]


def test_split_absorption_disagreement_is_logged_but_does_not_split(caplog):
    """Option B: when a weakly-classified continuation page disagrees with
    the currently-open group's type, that must be logged for visibility --
    but the split itself must not change as a result. Pure logging, no
    behavior change.
    """
    import logging

    caplog.set_level(logging.WARNING, logger="app.preprocessing.splitter")

    types = _doc_types([
        "TRIPARTITE AGREEMENT\nPage 1.",
        "This page mentions an authority letter in passing, deep in prose, "
        "not as its own header -- so it carries weak but not strong evidence.",
    ])

    assert types == [DocumentType.TRIPARTITE_AGREEMENT]
    assert len(types) == 1
    assert any(
        "possible cross-document absorption" in record.message
        for record in caplog.records
    )


def test_split_absorption_disagreement_is_returned_as_structured_warning():
    """The same disagreement must also be returned as an AbsorptionWarning,
    not just logged -- this is what a caller with a DB session (see
    document_processing/services.py) uses to flag the document for a human
    instead of relying on a console-only log line.
    """
    result = _split_full([
        "TRIPARTITE AGREEMENT\nPage 1.",
        "This page mentions an authority letter in passing, deep in prose, "
        "not as its own header -- so it carries weak but not strong evidence.",
    ])

    assert len(result.documents) == 1
    assert result.documents[0][0] == DocumentType.TRIPARTITE_AGREEMENT
    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.document_index == 0
    assert warning.document_type == DocumentType.TRIPARTITE_AGREEMENT
    assert warning.page_number == 1
    assert warning.weakly_matched_type == DocumentType.AUTHORITY_LETTER


def test_split_no_warnings_when_every_document_matches_strongly():
    """The common, healthy case: no absorption disagreement anywhere must
    produce an empty warnings list, not just an absent log line.
    """
    result = _split_full([
        "TRIPARTITE AGREEMENT\nPage 1.",
        "AUTHORITY LETTER\nPage 2.",
    ])

    assert len(result.documents) == 2
    assert result.warnings == []


def test_split_multiple_absorbed_pages_in_one_group_produce_one_warning_each():
    """Several disagreeing pages absorbed into the same open group must each
    surface their own warning, all indexed to the same document.
    """
    result = _split_full([
        "TRIPARTITE AGREEMENT\nPage 1.",
        "This page mentions an authority letter in passing, deep in prose, "
        "not as its own header -- so it carries weak but not strong evidence.",
        "This page mentions a business requirement document in passing, deep "
        "in prose, not as its own header -- weak evidence only.",
    ])

    assert len(result.documents) == 1
    assert len(result.warnings) == 2
    assert {w.document_index for w in result.warnings} == {0}
    assert {w.weakly_matched_type for w in result.warnings} == {
        DocumentType.AUTHORITY_LETTER,
        DocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
    }


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