"""Deterministic field extraction from OCR text.

The analysis pipeline turns the raw text of a document into a normalized set of
structured fields. No machine learning is involved: every field is produced by a
regex pattern and a post-processing step, so results are reproducible and
explainable. The document type is inferred first (``detect_document_type``) and
selects the extractor whose patterns best fit the document's expected layout.
"""

import re
from datetime import date, datetime
from typing import Any, Callable

from app.document_analysis.constants import AnalyzedDocumentType
from app.document_analysis.exceptions import UnsupportedDocumentType


def _parse_amount(raw: str) -> float | None:
    """Parse a monetary string into a float.

    Handles thousands separators and decimal marks in both ``1,250.50`` and
    ``1.250,50`` conventions, as well as optional currency prefixes.

    Args:
        raw: Raw amount text (e.g. ``"1,250.50"``, ``"EUR 45,000.00"``).

    Returns:
        The amount as a float, or ``None`` when it cannot be parsed.
    """
    cleaned = raw.strip().replace(" ", "")
    cleaned = re.sub(r"^(?:EUR|USD|GBP|€|£|\$)", "", cleaned)
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts) > 1 and len(parts[-1]) == 3 and all(
            1 <= len(part) <= 3 for part in parts[:-1]
        ):
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return None if value != value or value in (float("inf"), float("-inf")) else value


def _parse_date(raw: str) -> date | None:
    """Parse a date string into a :class:`datetime.date`.

    Supports ISO (``YYYY-MM-DD``), slash (``DD/MM/YYYY``) and textual month
    (``DD Mon YYYY``) representations, which cover the realistic OCR output of
    financial documents.

    Args:
        raw: Raw date text.

    Returns:
        The parsed date, or ``None`` when it cannot be parsed.
    """
    value = raw.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _as_iso_date(raw: str) -> str | None:
    """Parse a date and return it as an ISO ``YYYY-MM-DD`` string."""
    parsed = _parse_date(raw)
    return parsed.isoformat() if parsed is not None else None


def _as_float(raw: str) -> float | None:
    """Parse an amount and return it as a float."""
    return _parse_amount(raw)


def _as_int(raw: str) -> int | None:
    """Parse the first integer found in a string."""
    match = re.search(r"\d+", raw)
    return int(match.group()) if match else None


def _as_statement_period(raw: str) -> dict[str, str] | None:
    """Parse ``<start> - <end>`` period text into a structured dict.

    Returns ``None`` unless both bounds parse, keeping the extracted value
    strictly typed for the consistency rules.
    """
    match = re.search(r"(.+?)\s*(?:-|—|to)\s*(.+)", raw, flags=re.IGNORECASE)
    if match is None:
        return None
    start = _parse_date(match.group(1))
    end = _parse_date(match.group(2))
    if start is None or end is None:
        return None
    return {"start": start.isoformat(), "end": end.isoformat()}


def _as_salary_month(raw: str) -> str | None:
    """Normalize a salary month into ``YYYY-MM``.

    Accepts ISO (``2026-01``), slash (``2026/01``) and ``January 2026`` forms.
    """
    iso = re.search(r"(\d{4})[-/](\d{1,2})", raw)
    if iso:
        year, month = iso.groups()
        return f"{year}-{int(month):02d}"
    textual = re.search(r"([A-Za-z]+)\s+(\d{4})", raw)
    if textual:
        try:
            month = datetime.strptime(textual.group(1), "%B").month
        except ValueError:
            try:
                month = datetime.strptime(textual.group(1), "%b").month
            except ValueError:
                return None
        return f"{textual.group(2)}-{month:02d}"
    return None


def _trim(raw: str) -> str:
    """Trim whitespace and trailing punctuation from a raw field value."""
    return raw.strip().strip(":;|").strip()


class RegexExtractor:
    """Extractor driven by a declarative map of field patterns.

    Subclasses declare the analysed document type, the regex for every field and
    an optional post-processor that converts the raw match into the normalized
    value. Fields that do not match are omitted from the result so downstream
    scoring can count them as missing.
    """

    document_type: AnalyzedDocumentType
    _patterns: dict[str, re.Pattern]
    _post: dict[str, Callable[[str], Any]] = {}

    def extract(self, text: str) -> dict[str, Any]:
        """Return the normalized fields extracted from ``text``.

        Args:
            text: Raw OCR text of the document.

        Returns:
            A dict mapping field name to its normalized value.
        """
        fields: dict[str, Any] = {}
        for name, pattern in self._patterns.items():
            match = pattern.search(text)
            if match is None:
                continue
            value = _trim(match.group(1))
            if not value:
                continue
            post = self._post.get(name)
            fields[name] = post(value) if post is not None else value
        return fields


class BankStatementExtractor(RegexExtractor):
    """Extracts structured fields from a bank statement."""

    document_type = AnalyzedDocumentType.BANK_STATEMENT

    _patterns = {
        "account_holder": re.compile(
            r"(?:Account Holder|Account Name)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "account_number": re.compile(
            r"(?:Account Number|A/?C No\.?|Account No\.?)\s*[:|-]?\s*([A-Za-z0-9\-/ ]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "iban": re.compile(
            r"\bIBAN\b\s*[:|-]?\s*([A-Z]{2}\d{2}[A-Z0-9]{10,30})",
            re.IGNORECASE,
        ),
        "bank_name": re.compile(
            r"(?:Bank Name|Bank)\s*[:|-]?\s*(?!Statement\b)(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "statement_period": re.compile(
            r"(?:Statement Period|Period|For the period)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "opening_balance": re.compile(
            r"(?:Opening Balance|Opening)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "closing_balance": re.compile(
            r"(?:Closing Balance|Closing)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "total_credits": re.compile(
            r"(?:Total Credits|Total In|Credits)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "total_debits": re.compile(
            r"(?:Total Debits|Total Out|Debits)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "currency": re.compile(
            r"(?:Currency|CCY)\s*[:|-]?\s*([A-Z]{3})",
            re.IGNORECASE | re.MULTILINE,
        ),
        "transaction_count": re.compile(
            r"(?:Transactions|No\.? of Transactions)\s*[:|-]?\s*(\d+)",
            re.IGNORECASE | re.MULTILINE,
        ),
    }

    _post = {
        "opening_balance": _as_float,
        "closing_balance": _as_float,
        "total_credits": _as_float,
        "total_debits": _as_float,
        "statement_period": _as_statement_period,
        "transaction_count": _as_int,
    }


class PayslipExtractor(RegexExtractor):
    """Extracts structured fields from a salary slip / payslip."""

    document_type = AnalyzedDocumentType.PAYSLIP

    _patterns = {
        "employee_name": re.compile(
            r"(?:Employee Name|Name of Employee)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "employee_id": re.compile(
            r"(?:Employee ID|Emp\.? ID|Staff No\.?|Personnel No\.?)\s*[:|-]?\s*([A-Za-z0-9\-/]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "employer_name": re.compile(
            r"(?:Employer Name|Employer|Company)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "gross_salary": re.compile(
            r"(?:Gross Salary|Gross Pay|Gross)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "net_salary": re.compile(
            r"(?:Net Salary|Net Pay|Net)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "salary_month": re.compile(
            r"(?:Salary Month|Pay Period|Month)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "payment_date": re.compile(
            r"(?:Payment Date|Pay Date|Date Paid)\s*[:|-]?\s*([A-Za-z0-9\-/.]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
    }

    _post = {
        "gross_salary": _as_float,
        "net_salary": _as_float,
        "salary_month": _as_salary_month,
        "payment_date": _as_iso_date,
    }


class IdentityExtractor(RegexExtractor):
    """Extracts basic identity fields from a national ID or passport."""

    document_type = AnalyzedDocumentType.ID_DOCUMENT

    _patterns = {
        "full_name": re.compile(
            r"(?:Full Name|Name)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "date_of_birth": re.compile(
            r"(?:Date of Birth|DOB|Birth Date)\s*[:|-]?\s*([A-Za-z0-9\-/.]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "document_number": re.compile(
            r"(?:ID Number|Document Number|National ID No\.?|Passport No\.?)\s*[:|-]?\s*([A-Za-z0-9\-]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "nationality": re.compile(
            r"(?:Nationality|Nationality Code)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "issue_date": re.compile(
            r"(?:Issue Date|Date of Issue)\s*[:|-]?\s*([A-Za-z0-9\-/.]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "expiry_date": re.compile(
            r"(?:Expiry Date|Date of Expiry|Valid Until|Expires)\s*[:|-]?\s*([A-Za-z0-9\-/.]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
    }

    _post = {
        "date_of_birth": _as_iso_date,
        "issue_date": _as_iso_date,
        "expiry_date": _as_iso_date,
    }


class TaxExtractor(RegexExtractor):
    """Extracts basic fields from a tax document."""

    document_type = AnalyzedDocumentType.TAX_DOCUMENT

    _patterns = {
        "taxpayer_name": re.compile(
            r"(?:Taxpayer Name|Taxpayer's Name|Taxpayer)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "tax_reference_number": re.compile(
            r"(?:Tax Reference Number|Tax Reference|UTR|Tax ID)\s*[:|-]?\s*([A-Za-z0-9\-]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "tax_year": re.compile(
            r"(?:Tax Year|Assessment Year|Year)\s*[:|-]?\s*((?:19|20)\d{2})",
            re.IGNORECASE | re.MULTILINE,
        ),
        "gross_income": re.compile(
            r"(?:Gross Income|Total Income|Adjusted Gross Income)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "total_tax": re.compile(
            r"(?:Total Tax|Tax Due|Income Tax|Tax Payable)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "currency": re.compile(
            r"(?:Currency|CCY)\s*[:|-]?\s*([A-Z]{3})",
            re.IGNORECASE | re.MULTILINE,
        ),
    }

    _post = {
        "tax_year": _as_int,
        "gross_income": _as_float,
        "total_tax": _as_float,
    }


#: Detection keywords per analysed document type. Weights express how strongly a
#: keyword identifies the type; scoring is order-independent and deterministic.
_DETECTION_KEYWORDS: dict[AnalyzedDocumentType, list[tuple[str, int]]] = {
    AnalyzedDocumentType.BANK_STATEMENT: [
        ("account statement", 3),
        ("bank statement", 3),
        ("opening balance", 2),
        ("closing balance", 2),
        ("iban", 2),
        ("transactions", 1),
    ],
    AnalyzedDocumentType.PAYSLIP: [
        ("payslip", 3),
        ("pay slip", 3),
        ("salary slip", 3),
        ("gross salary", 2),
        ("net salary", 2),
        ("payment date", 1),
        ("employee id", 1),
    ],
    AnalyzedDocumentType.ID_DOCUMENT: [
        ("national id", 3),
        ("identity card", 3),
        ("passport", 3),
        ("date of birth", 2),
        ("expiry date", 2),
        ("id number", 1),
    ],
    AnalyzedDocumentType.TAX_DOCUMENT: [
        ("tax return", 3),
        ("tax reference", 2),
        ("taxpayer", 2),
        ("tax year", 2),
        ("income tax", 1),
    ],
}

#: Extractors available for each analysed document type.
_EXTRACTORS: dict[AnalyzedDocumentType, RegexExtractor] = {
    AnalyzedDocumentType.BANK_STATEMENT: BankStatementExtractor(),
    AnalyzedDocumentType.PAYSLIP: PayslipExtractor(),
    AnalyzedDocumentType.ID_DOCUMENT: IdentityExtractor(),
    AnalyzedDocumentType.TAX_DOCUMENT: TaxExtractor(),
}


def detect_document_type(text: str) -> AnalyzedDocumentType:
    """Infer the analysed document type from keyword scoring.

    Every keyword present in the text contributes its weight to the matching
    document type; the type with the highest total wins. Ties resolve to the
    first-defined type, keeping the result deterministic.

    Deliberately only recognises the 4 categories with a real extractor
    below -- it is not, and should not become, a classifier for the real
    required-document checklist (Tripartite Agreement, Authority Letter,
    etc.). That vocabulary belongs to the splitter
    (``app/preprocessing/splitter.py``) and is already reliably captured on
    ``document.document_type``; widening this table to match it without
    adding a real extractor for each type would only relabel documents this
    module still can't extract anything from. When this returns ``UNKNOWN``,
    ``DocumentAnalysisService`` falls back to the splitter's own
    classification to distinguish "recognised, no extractor yet" from
    "genuinely couldn't classify" -- see
    ``DocumentAnalysisService._recognized_checklist_type``.

    Args:
        text: Raw OCR text of the document.

    Returns:
        The inferred analysed document type, or ``UNKNOWN``.
    """
    lowered = text.lower()
    best_type = AnalyzedDocumentType.UNKNOWN
    best_score = 0
    for document_type, keywords in _DETECTION_KEYWORDS.items():
        score = sum(weight for keyword, weight in keywords if keyword in lowered)
        if score > best_score:
            best_score = score
            best_type = document_type
    return best_type


def extract_fields(text: str, document_type: AnalyzedDocumentType) -> dict[str, Any]:
    """Extract normalized fields from ``text`` for an analysed document type.

    Args:
        text: Raw OCR text of the document.
        document_type: Analysed document type selecting the extractor.

    Returns:
        The normalized extracted fields.

    Raises:
        UnsupportedDocumentType: When the type has no extractor (e.g. unknown).
    """
    extractor = _EXTRACTORS.get(document_type)
    if extractor is None:
        raise UnsupportedDocumentType()
    return extractor.extract(text)
