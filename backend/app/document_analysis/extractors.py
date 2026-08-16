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


#: Platform names docs/Master_Rules_Combined.md requires the agreement to
#: name explicitly (Section 7, "Platform Terminology"). Matched literally
#: rather than via a labeled regex since the term appears embedded in prose,
#: not after a "Field:" label.
_KNOWN_PLATFORM_NAMES: tuple[str, ...] = ("Digital Muhasil", "PayMin", "Paymere BCX")


def _as_platform_name(raw: str) -> str | None:
    """Return whichever known platform name is present in ``raw``, if any."""
    for name in _KNOWN_PLATFORM_NAMES:
        if name.lower() in raw.lower():
            return name
    return None


class BilateralAgreementExtractor(RegexExtractor):
    """Extracts structured fields from a Bilateral Agreement (SLA).

    Field patterns are based on docs/Master_Rules_Combined.md Section 7
    ("Bilateral Agreement (SLA)") rather than a labeled-field layout the way
    the other extractors are, since the master rules describe this document
    as prose/section-numbered rather than a "Label: value" form. Real-sample
    validation against Confidential Data/ is still pending -- see the
    docstring note in docs/IMPLEMENTATION_ROADMAP.md Phase 1 on why a single
    pattern per type can't be trusted blind; patterns here should be revisited
    once validated against actual OCR text.
    """

    document_type = AnalyzedDocumentType.BILATERAL_AGREEMENT

    _patterns = {
        "organization_name": re.compile(
            r"(?:Department|Organization|Organisation)\s*(?:Name)?\s*[:|-]\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "platform_name": re.compile(
            r"(Digital Muhasil|PayMin|Paymere BCX)",
            re.IGNORECASE,
        ),
        "transaction_charges": re.compile(
            # Anchored to "Section 5.2" specifically (not a bare "Section 5" or
            # "Transaction Charges" heading, which docs/Master_Rules_Combined.md
            # Section 7 shows appearing earlier as a section title on its own
            # line and would otherwise match first and capture the title, not
            # the actual PKR charge line 5.2 introduces).
            r"Section\s*5\.2\s*[:.\-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "account_holder": re.compile(
            r"(?:Account Title|Account Holder|Account Name)\s*[:|-]?\s*(.+)",
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
        "effective_date": re.compile(
            r"(?:Effective Date|Date of Agreement)\s*[:|-]?\s*([A-Za-z0-9\-/.]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
    }

    _post = {
        "platform_name": _as_platform_name,
        "effective_date": _as_iso_date,
    }


class AuthorityLetterExtractor(RegexExtractor):
    """Extracts structured fields from an Authority Letter.

    Real Authority Letters follow a standard prose template -- confirmed
    against two independent real departments in Confidential Data/, almost
    word-for-word identical: "It is hereby authorized that Mr. <name>,
    <designation> is authorized to deal with and conduct correspondence and
    matter(s) related to 1-Link and the Khyber Pakhtunkhwa Information
    Technology Board (KPITB) on (the) behalf of <organization>." Only this
    prose-embedded variant is validated. docs/IMPLEMENTATION_ROADMAP.md also
    describes a labeled-block variant ("Name:"/"Designation:" fields) that
    has not yet turned up in a real sample -- not built blind (see the
    roadmap's Phase 1 "why this can't be done blind" note); a document using
    that form will simply extract nothing here rather than guess.

    Unlike docs/Master_Rules_Combined.md Section 2 ("account maintenance
    details must appear at the top"), neither real sample reviewed so far
    carries any bank account information at all -- account_holder/
    account_number/iban are extracted opportunistically (reusing the same
    patterns as BilateralAgreementExtractor) but are not critical fields,
    see constants.CRITICAL_FIELDS.
    """

    document_type = AnalyzedDocumentType.AUTHORITY_LETTER

    _patterns = {
        "focal_person_name": re.compile(
            r"Mr\.?\s+([A-Za-z][A-Za-z.'\- ]*?)\s*[,(]",
        ),
        "focal_person_designation": re.compile(
            r"Mr\.?\s+[A-Za-z][A-Za-z.'\- ]*?[,(]\s*([^,()]+?)(?=[,()]|\s+is\s+authorized)",
            re.IGNORECASE,
        ),
        "organization_name": re.compile(
            r"on\s+(?:the\s+)?behalf\s+of\s+([^.\n]+)",
            re.IGNORECASE,
        ),
        "account_holder": re.compile(
            r"(?:Account Title|Account Holder|Account Name)\s*[:|-]?\s*(.+)",
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
    }


class BusinessRequirementDocumentExtractor(RegexExtractor):
    """Extracts presence signals from a Business Requirement Document (BRD).

    docs/Master_Rules_Combined.md Section 10 requires the BRD to (a) confirm
    that payments are required to be digitized and (b) identify/list the
    revenue-generating services being digitized. Real BRDs (three independent
    departments, Confidential Data/) satisfy both requirements but express
    them with no shared template at all -- unlike Bilateral Agreement or
    Authority Letter, there is no labeled field or single consistent sentence
    grammar here; department history, section headers and list format (a
    numbered list, a categorized bullet breakdown, or unstructured prose all
    turned up across the three samples) differ per department. So neither
    field extracts a *value* in the usual sense -- both are presence
    detectors whose captured group is the anchor phrase that triggered them,
    kept as the field's value for a human reviewer's context.

    digitization_intent_confirmed is anchored on "KPITB('s) Fin(-)Tech Unit"
    -- confirmed verbatim (case/spacing aside) in all three real samples,
    the one genuinely consistent element, the same way Authority Letter had
    one consistent core sentence. See constants.CRITICAL_FIELDS for why only
    this field, not revenue_services_listed, is treated as critical.
    """

    document_type = AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT

    _patterns = {
        "digitization_intent_confirmed": re.compile(
            r"(KPITB'?S?\s+Fin\s*Tech\s+Unit)",
            re.IGNORECASE,
        ),
        "revenue_services_listed": re.compile(
            r"(sources? of income|services offered|revenue[- ]generating services|prescribed fees?)",
            re.IGNORECASE,
        ),
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

class AccountMaintenanceCertificateExtractor(RegexExtractor):
    """Extracts structured fields from an Account Maintenance Certificate.

    A bank certificate attesting an account's details: account title, account
    number, IBAN, issuing bank and branch. Field names deliberately mirror the
    cross-document consistency rules (``account_holder``, ``account_number``,
    ``iban``) so the normalization stage can compare them against the Bilateral
    and Tripartite agreements.
    """

    document_type = AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE

    _patterns = {
        "account_holder": re.compile(
            r"(?:Account Title|Title of Account|Account Holder|Account Name)\s*[:|-]?\s*(.+)",
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
            r"\bBank(?: Name)?\s*:\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "branch_name": re.compile(
            r"(?:Branch Name|Branch)\s*:\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "issue_date": re.compile(
            r"(?:Date of Issue|Issue Date|Issued On|Issuance Date)\s*[:|-]?\s*([A-Za-z0-9\-/.]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
    }

    _post = {
        "issue_date": _as_iso_date,
    }


class TripartiteAgreementExtractor(RegexExtractor):
    """Extracts structured fields from a Tripartite Agreement.

    Captures the three named parties (1-Link, KPITB, the sub-biller) and the
    bank details section (account title, account number, branch) that must
    match the Account Maintenance Certificate. Field names follow the
    cross-document consistency rules (``account_holder``, ``account_number``,
    ``branch_code``).
    """

    document_type = AnalyzedDocumentType.TRIPARTITE_AGREEMENT

    #: Patterns are label-anchored and deliberately tolerant of OCR noise:
    #: party names are captured up to the next comma, newline or the standard
    #: "(hereinafter referred to as ...)" clause. Tune against real samples.
    _patterns = {
        "party_1link": re.compile(
            r"((?:1LINK|1-LINK|ONE[-\s]?LINK|ONELINK)[^,\n]*?)(?=\s*\(hereinafter|\s*,|\s*\n|$)",
            re.IGNORECASE,
        ),
        "party_kpitb": re.compile(
            r"((?:KHYBER PAKHTUNKHWA INFORMATION TECHNOLOGY BOARD|KPITB))(?=[\s,])",
            re.IGNORECASE,
        ),
        "party_subbiller": re.compile(
            r"(.{2,}?)\s*\([^)]*?[Ss]ub[-\s]?[Bb]iller[^)]*?\)",
            re.IGNORECASE,
        ),
        "account_holder": re.compile(
            r"(?:Account Title|Title of Account|Account Holder)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "account_number": re.compile(
            r"(?:Account Number|A/?C No\.?|Account No\.?)\s*[:|-]?\s*([A-Za-z0-9\-/ ]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "branch_code": re.compile(
            r"(?:Branch Code|Branch)\s*:\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
    }


#: Extractors available for each analysed document type.
_EXTRACTORS: dict[AnalyzedDocumentType, RegexExtractor] = {
    AnalyzedDocumentType.BANK_STATEMENT: BankStatementExtractor(),
    AnalyzedDocumentType.PAYSLIP: PayslipExtractor(),
    AnalyzedDocumentType.ID_DOCUMENT: IdentityExtractor(),
    AnalyzedDocumentType.TAX_DOCUMENT: TaxExtractor(),
    AnalyzedDocumentType.BILATERAL_AGREEMENT: BilateralAgreementExtractor(),
    AnalyzedDocumentType.AUTHORITY_LETTER: AuthorityLetterExtractor(),
    AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE: AccountMaintenanceCertificateExtractor(),
    AnalyzedDocumentType.TRIPARTITE_AGREEMENT: TripartiteAgreementExtractor(),
    AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT: BusinessRequirementDocumentExtractor(),
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
