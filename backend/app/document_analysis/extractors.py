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


def _as_iso_date_dotted(raw: str) -> str | None:
    """Parse a dot-separated ``DD.MM.YYYY`` date (the format printed on a real
    Pakistani CNIC) and return it as an ISO ``YYYY-MM-DD`` string.

    Deliberately separate from :func:`_as_iso_date`/:func:`_parse_date`: the
    real CNIC samples this was built against use dots, not the slash/ISO/
    textual-month formats those already handle, and adding dots there would
    change parsing behaviour for every other extractor that reuses them.
    """
    try:
        return datetime.strptime(raw.strip(), "%d.%m.%Y").date().isoformat()
    except ValueError:
        return None


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


def _as_single_line(raw: str) -> str:
    """Collapse internal newlines/runs of whitespace into single spaces.

    Some real captures span an OCR line break (e.g. a name wrapped mid-value);
    the raw group otherwise keeps the literal newline.
    """
    return re.sub(r"\s+", " ", raw).strip()


#: Field labels the bank-account block parser understands, ordered most specific
#: first. Each entry maps a label pattern to the field key it feeds. Built
#: against the real cached layouts (Confidential Data/.ocr_cache/): the AMC
#: copies interleave label/value lines (same-line "Label: value", dotted-leader
#: "Label:... value", or bare label followed by its value on the next line,
#: sometimes wrapped over several lines); the Tripartite copy stacks a column
#: table (header block, then a value block mapped positionally). See
#: ``_extract_bank_account_block`` for the two scan passes.
_BANK_LABELS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"account\s*no\.?\s*/?\s*iban", re.IGNORECASE), "account_number"),
    (re.compile(r"iban\s*/?\s*account\s*no\.?", re.IGNORECASE), "account_number"),
    (re.compile(r"title\s*of\s*account", re.IGNORECASE), "account_holder"),
    (re.compile(r"account\s*title", re.IGNORECASE), "account_holder"),
    (re.compile(r"account\s*holder", re.IGNORECASE), "account_holder"),
    (re.compile(r"account\s*name", re.IGNORECASE), "account_holder"),
    (re.compile(r"account\s*number", re.IGNORECASE), "account_number"),
    (re.compile(r"account\s*no\.?", re.IGNORECASE), "account_number"),
    (re.compile(r"(?:a/?c|ac)\s*no\.?", re.IGNORECASE), "account_number"),
    (re.compile(r"bank\s*name", re.IGNORECASE), "bank_name"),
    (re.compile(r"iban", re.IGNORECASE), "iban"),
)

#: Table row-index headers ("S#", "S.No", "Sr. No", ...). A column block with
#: this header carries a leading row number that must never be mistaken for an
#: account number value.
_ROW_INDEX_HEADER = re.compile(
    r"^(?:s\s*[/#.]?\s*no\.?|s\s*#|sr\.?\s*no\.?|s/?no\.?|#)\s*$", re.IGNORECASE
)


def _match_label(line: str) -> tuple[str, str] | None:
    """Return ``(field_key, remainder)`` when ``line`` starts with a known
    bank-account field label, else ``None``.

    ``remainder`` is everything after the label, before any value extraction
    (it may be empty for a bare label whose value is on the next line).
    """
    s = line.strip()
    if not s:
        return None
    for pattern, key in _BANK_LABELS:
        match = pattern.match(s)
        if match is not None:
            return key, s[match.end():]
    return None


def _is_iban_like(value: str) -> bool:
    """Return True when ``value`` is a structurally valid IBAN (ignoring OCR
    line-break spaces)."""
    cleaned = re.sub(r"\s+", "", value)
    return bool(re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", cleaned))


def _is_value_like_line(line: str) -> bool:
    """Return True when a line reads as a standalone field value rather than
    prose or a label continuation.

    Used to stop wrapped multi-line value capture before the next field's
    label (e.g. a CNIC or date that follows an account title in a certificate).
    """
    s = line.strip()
    if not s or _match_label(s) is not None:
        return False
    if re.fullmatch(r"\d{4,}", s):
        return True
    if re.fullmatch(r"\d{5}-\d{7}-\d", s):
        return True
    if re.search(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}", s):
        return True
    if re.search(r"\b(?:PKR|USD|EUR|Rs\.?)\b", s, re.IGNORECASE):
        return True
    if re.search(r"\b[A-Z]{2}\d{2}[A-Z0-9]{8,}\b", s):
        return True
    if re.search(r"\d{1,3}(?:,\d{3})+\.\d{2}", s):
        return True
    return False


def _looks_like_column_header(line: str) -> bool:
    """Return True when a line plausibly continues a column-header run (a
    short, non-numeric caption), i.e. it should be skipped as OCR noise between
    recognized headers rather than breaking the run or starting the value
    block."""
    s = line.strip()
    if not s or len(s) > 20:
        return False
    if s[0].isdigit() or s.startswith(("(", "[", "PK", "PN")):
        return False
    if re.fullmatch(r"[\d.,]+", s):
        return False
    return True


def _normalize_account_holder(raw: str) -> str | None:
    """Clean a captured account-holder value, or return ``None`` when it is not
    a real account title (e.g. a captured field label or a bare number)."""
    value = _as_single_line(raw).strip().strip(".,:;|-").strip()
    if not value or _is_header(value) or value.isdigit():
        return None
    return value


def _normalize_account_number(raw: str) -> tuple[str | None, str | None]:
    """Split a captured account-number value into ``(account_number, iban)``.

    Handles the real value shapes seen in the OCR cache: a bare account number
    (an all-digit value), a combined ``<number>/<IBAN>`` pair, an IBAN alone
    (the Tripartite account slot), and an account number with a parenthetical
    IBAN tail. An all-digit value of length <= 3 is a row index / page marker,
    never an account number.
    """
    value = raw.strip().rstrip(".:;-/ ").strip()
    iban_tail: str | None = None
    paren = re.search(r"\((.+)\)?\s*$", value)
    if paren is not None and paren.start() > 0:
        tail = paren.group(1).strip()
        head = value[: paren.start()].strip()
        if _is_iban_like(tail):
            iban_tail = re.sub(r"\s+", "", tail)
            value = head
    if "/" in value:
        left, right = (part.strip() for part in value.split("/", 1))
        if _is_iban_like(right):
            return left or None, re.sub(r"\s+", "", right)
        if _is_iban_like(left):
            return right or None, re.sub(r"\s+", "", left)
        if re.search(r"\d", value) and len(value) >= 4:
            return value, iban_tail
        return None, iban_tail
    if _is_iban_like(value):
        return None, re.sub(r"\s+", "", value)
    if value.isdigit():
        if len(value) <= 3:
            return None, iban_tail
        return value, iban_tail
    if (
        re.search(r"\d", value)
        and len(value) >= 4
        and re.fullmatch(r"[A-Za-z0-9\-/ ]+", value)
    ):
        return value, iban_tail
    return None, iban_tail


def _normalize_iban(raw: str) -> str | None:
    """Clean a captured IBAN value, or return ``None`` when it is not a valid
    IBAN shape."""
    value = re.sub(r"\s+", "", raw.strip().rstrip(".:;-/ ").strip())
    return value if _is_iban_like(value) else None


def _emit(key: str, raw: str) -> list[tuple[str, str]]:
    """Normalize one raw capture and return the normalized captures to record.

    ``_acc_no_fallback`` records an IBAN-only value captured under an
    account-number label; ``_extract_bank_account_block`` promotes it to
    ``account_number`` only when no plain account number was found anywhere in
    the document (the Tripartite column-table case, where the account slot
    holds an IBAN).
    """
    if key == "account_holder":
        value = _normalize_account_holder(raw)
        return [("account_holder", value)] if value else []
    if key == "account_number":
        account, iban = _normalize_account_number(raw)
        emits: list[tuple[str, str]] = []
        if account is not None:
            emits.append(("account_number", account))
        elif iban is not None:
            emits.append(("_acc_no_fallback", iban))
        if iban is not None:
            emits.append(("iban", iban))
        return emits
    if key == "iban":
        value = _normalize_iban(raw)
        return [("iban", value)] if value else []
    return []


def _is_header(line: str) -> bool:
    """Return True when a line is a recognized field label (bank-account label
    or a table row-index header)."""
    s = line.strip()
    return _match_label(s) is not None or bool(_ROW_INDEX_HEADER.match(s))


def _consume_value_lines(
    lines: list[str], start: int, cap: int
) -> tuple[list[str], int]:
    """Collect the value following a bare label line.

    ``lines[start]`` is the first line after the label. Stops at the next
    recognized label, and -- after the first line -- before a line that itself
    looks like a field value (the wrapped-title continuation must not absorb
    the next field's label). Returns ``(parts, next_index)``.
    """
    parts: list[str] = []
    n = len(lines)
    j = start
    while j < n and len(parts) < cap:
        line = lines[j].strip()
        if not line:
            j += 1
            continue
        if _match_label(line) is not None:
            break
        nxt = lines[j + 1].strip() if j + 1 < n else ""
        if len(parts) >= 1 and (_is_value_like_line(line) or _is_value_like_line(nxt)):
            break
        parts.append(line)
        j += 1
    return parts, j


def _extract_column_block(
    lines: list[str],
) -> tuple[list[tuple[str, str, int]], int, int] | tuple[None, None, None]:
    """Detect a stacked column-block bank table (header block followed by a
    positionally-mapped value block) and return its normalized captures.

    Returns ``(captures, block_start, block_end)`` where ``captures`` is a list
    of ``(field_key, value, line_index)`` and ``[block_start, block_end)`` is
    the region to skip in the interleaved pass. Returns ``(None, None, None)``
    when no valid block exists.

    Header lines are matched against ``_BANK_LABELS``/``_ROW_INDEX_HEADER``;
    unrecognized short caption lines between them are treated as OCR noise and
    skipped (the real Tripartite sample has an ``IENT`` column between ``Bank
    Name`` and ``Account Title``). Values are mapped positionally by recognized
    header, so noise headers do not consume a value. The block is only accepted
    when its account-number slot normalizes to something real, so a shifted
    mapping (or a plain "label/value" pair misread as a table) is rejected
    rather than emitted as wrong data.
    """
    n = len(lines)
    for start in range(n):
        if not _is_header(lines[start]):
            continue
        header_keys: list[str] = []
        j = start
        while j < n and len(header_keys) < 6 and j - start < 10:
            line = lines[j].strip()
            if not line:
                j += 1
                continue
            matched = _match_label(line)
            if matched is not None:
                header_keys.append(matched[0])
                j += 1
                continue
            if _ROW_INDEX_HEADER.match(line):
                header_keys.append("_row_index")
                j += 1
                continue
            if _looks_like_column_header(line):
                j += 1
                continue
            break
        if len(header_keys) < 2:
            continue
        values: list[str] = []
        k = j
        while k < n and len(values) < len(header_keys):
            line = lines[k].strip()
            if line:
                values.append(line)
            k += 1
        if len(values) != len(header_keys):
            continue
        account_value = None
        for key, value in zip(header_keys, values):
            if key == "account_number":
                account_value = value
        if account_value is None:
            continue
        account_norm, iban_norm = _normalize_account_number(account_value)
        if account_norm is None and iban_norm is None:
            continue
        captures: list[tuple[str, str, int]] = []
        for key, value in zip(header_keys, values):
            if key in ("_row_index", "bank_name"):
                continue
            emits = _emit(key, value)
            for emit_key, emit_value in emits:
                captures.append((emit_key, emit_value, start))
        return captures, start, k
    return None, None, None


def _interleaved_scan(
    lines: list[str], skip_start: int | None, skip_end: int | None
) -> list[tuple[str, str, int]]:
    """Scan label/value-interleaved bank fields, skipping a detected
    column-block region.

    Handles the same-line form (``Label: value`` and dotted-leader ``Label:...
    value``, e.g. the ZTBL page of GDA copy2) and the bare-label-then-value
    form (e.g. the wrapped title in NBP copy3). First occurrence in document
    order wins per field, so a page-1 value is never overwritten by a
    page-2 one.
    """
    captures: list[tuple[str, str, int]] = []
    n = len(lines)
    i = 0
    while i < n:
        if skip_start is not None and skip_start <= i < skip_end:
            i += 1
            continue
        line = lines[i]
        if not line:
            i += 1
            continue
        matched = _match_label(line)
        if matched is None:
            i += 1
            continue
        key, remainder = matched
        if key not in ("account_holder", "account_number", "iban"):
            i += 1
            continue
        raw = re.sub(r"^[:.\-*\s]+", "", remainder)
        if raw:
            i += 1
        else:
            parts, i = _consume_value_lines(
                lines, i + 1, cap=3 if key == "account_holder" else 1
            )
            raw = " ".join(parts)
        if not raw:
            continue
        for emit_key, emit_value in _emit(key, raw):
            captures.append((emit_key, emit_value, i - 1))
    return captures


def _extract_bank_account_block(text: str) -> dict[str, str]:
    """Extract the bank-account block (account_holder, account_number, iban)
    from OCR text using the two structural layouts seen in the real cache:
    a stacked column table and interleaved label/value lines.

    Every value is normalized and shape-guarded -- a captured string that is a
    known field label, an all-digit row index of length <= 3, or any value that
    normalizes to nothing is rejected rather than emitted. Account number takes
    the first plain-number capture in document order; an IBAN-only capture
    under an account-number label is promoted to account_number only when no
    plain number exists anywhere in the document.
    """
    lines = [line.strip() for line in text.splitlines()]
    column_captures, block_start, block_end = _extract_column_block(lines)
    if column_captures is None:
        column_captures = []
    interleaved_captures = _interleaved_scan(lines, block_start, block_end)
    per_field: dict[str, tuple[str, int]] = {}
    for key, value, index in column_captures + interleaved_captures:
        if key == "_acc_no_fallback":
            continue
        if key not in per_field or index < per_field[key][1]:
            per_field[key] = (value, index)
    if "account_number" not in per_field:
        best: tuple[str, int] | None = None
        for key, value, index in column_captures + interleaved_captures:
            if key == "_acc_no_fallback" and (best is None or index < best[1]):
                best = (value, index)
        if best is not None:
            per_field["account_number"] = best
    return {
        key: per_field[key][0]
        for key in ("account_holder", "account_number", "iban")
        if key in per_field
    }


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
    against three independent real departments in Confidential Data/:
    "It is hereby authorized that Mr. <name>, <designation> is authorized to
    deal with and conduct correspondence and matter(s) related to 1-Link and
    the Khyber Pakhtunkhwa Information Technology Board (KPITB) on (the)
    behalf of <organization>." Only this prose-embedded variant is
    validated. docs/IMPLEMENTATION_ROADMAP.md also describes a labeled-block
    variant ("Name:"/"Designation:" fields) that has not yet turned up in a
    real sample -- not built blind (see the roadmap's Phase 1 "why this
    can't be done blind" note); a document using that form will simply
    extract nothing here rather than guess.

    focal_person_name's stopping point is deliberately not limited to a
    comma or paren: a third real department (confirmed 2026-08-18, TMA Lal
    Dir Upper) phrases the sentence as "It is here by submitted that Mr.
    <name> CNIC# <number>... is authorized..." -- no designation clause at
    all, so neither delimiter ever appears. The pattern now also stops at a
    following "CNIC" or "is authorized", whichever comes first, without
    changing what it captures on the original two departments (both still
    hit their own comma/paren first). focal_person_designation is
    deliberately NOT loosened to match -- that department's real letter
    genuinely never states a designation, so it correctly keeps missing
    that field rather than guessing one from nearby text.

    Two bugs fixed 2026-08-19 (department decision, see CONTEXT.md), both
    tested directly against GDA Abbotabad's real cached text:

    focal_person_name/focal_person_designation previously matched only the
    literal "Mr" prefix; GDA Abbotabad's real letter uses "Dr." ("It is
    hereby authorized that Dr. Samar Hayat Khan..."), which never matched
    at all. Generalized to a small, evidence-grounded honorific set --
    Mr/Mrs/Ms/Dr, the only two actually seen across 4 real samples -- not
    an attempt to anticipate every possible honorific. Separately, GDA's
    designation ("Taxation Officer-I") sits on the line *after* the name,
    unlike the other 3 samples' same-line "Mr. <name>, <designation>"
    shape; both patterns' stopping lookahead now tolerates crossing exactly
    one newline before finding the comma, tested against all 4 real
    samples to confirm this doesn't change what the other 3 already
    correctly capture.

    organization_name previously captured "this" from GDA's real sentence
    ("...on behalf of this\nAuthority.") -- a genuine garbage capture, not
    an honest miss, since "this" doesn't identify the organization at all.
    The letter refers back to itself by pronoun instead of naming the org
    in this clause, unlike the other 3 real samples. Fixed via extract()
    below: when the primary pattern's capture is a generic backward
    reference ("this"/"the said"/"said", optionally followed by "authority"
    /"board"/"office"/"department"), fall back to the letterhead -- the
    first substantive line before the "AUTHORITY LETTER" title, skipping
    contact-info lines -- which correctly names the organization in all 4
    real samples. Scoped narrowly to the exact backward-reference shape
    confirmed real, not a general letterhead parser: the other 3 samples'
    letterheads vary too much in format to parse generically, and their
    primary "on behalf of X" capture already works, so they never reach
    this fallback at all.

    Unlike docs/Master_Rules_Combined.md Section 2 ("account maintenance
    details must appear at the top"), none of the four real samples
    reviewed carries any bank account information on the Authority Letter's
    own page -- account_holder/account_number/iban are extracted
    opportunistically (reusing the same patterns as
    BilateralAgreementExtractor) but are not critical fields, see
    constants.CRITICAL_FIELDS. Some samples do incidentally populate
    account_number from an absorbed, structurally separate Account-
    Maintenance-Certificate-looking page that lands in the same document
    group (a known, unfixed splitter absorption gap) -- opportunistic by
    design, so this doesn't threaten the critical fields' validated status.
    """

    document_type = AnalyzedDocumentType.AUTHORITY_LETTER

    #: Backward-reference phrases the "on behalf of X" sentence sometimes
    #: uses instead of literally naming the organization (confirmed real,
    #: GDA Abbotabad: "...on behalf of this\nAuthority." captures just
    #: "this"). Triggers the letterhead fallback in extract() below.
    _GENERIC_ORG_REFERENCE = re.compile(
        r"^(?:this|the said|said)(?:\s+(?:authority|board|office|department))?$",
        re.IGNORECASE,
    )
    #: Letterhead lines to skip when falling back -- contact details, not
    #: the organization's own name.
    _LETTERHEAD_SKIP = re.compile(
        r"^(?:Ph|Phone|Fax|Email|Govt\.?|Government)\b",
        re.IGNORECASE,
    )

    _patterns = {
        "focal_person_name": re.compile(
            r"(?:Mr|Mrs|Ms|Dr)\.?\s+([A-Za-z][A-Za-z.'\- ]*?)"
            r"(?=\s*[,(]|\n[^\n,()]{0,80}[,(]|\s+CNIC|\s+is\s+authorized)",
        ),
        "focal_person_designation": re.compile(
            r"(?:Mr|Mrs|Ms|Dr)\.?\s+[A-Za-z][A-Za-z.'\- ]*?"
            r"(?:[,(]|\n(?=[^\n,()]{0,80}[,(]))\n?\s*([^,()]+?)(?=[,()]|\s+is\s+authorized)",
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

    def extract(self, text: str) -> dict[str, Any]:
        fields = super().extract(text)
        org = fields.get("organization_name")
        if org and self._GENERIC_ORG_REFERENCE.match(org):
            fallback = self._letterhead_organization_name(text)
            if fallback:
                fields["organization_name"] = fallback
            else:
                del fields["organization_name"]
        return fields

    @classmethod
    def _letterhead_organization_name(cls, text: str) -> str | None:
        """Return the first substantive letterhead line, or ``None``.

        Scans the text before the "AUTHORITY LETTER" title for the first
        line that isn't blank, isn't contact info, and is long enough to
        plausibly be an organization name rather than an OCR artifact
        (confirmed real: GDA Abbotabad's letterhead has a stray one-
        character line above the org name).
        """
        header = text.split("AUTHORITY LETTER", 1)[0]
        for line in header.splitlines():
            candidate = line.strip()
            if len(candidate) < 8 or cls._LETTERHEAD_SKIP.match(candidate) or "@" in candidate:
                continue
            return candidate
        return None


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


class OneLinkLetterExtractor(RegexExtractor):
    """Extracts fields from whatever real-world document lands in the 1-Link
    Letter checklist slot.

    Real content doesn't match docs/Master_Rules_Combined.md Section 4's
    KYC-style form spec -- see CONTEXT.md for the full mismatch and the
    splitter root cause. This extractor is grounded in what's actually
    there (a signed "PARTICIPATION MEMORANDUM..."), not the unvalidated
    spec, and deliberately stays narrow: department decision, 2026-08-19
    (see CONTEXT.md) -- extract only what's clearly critical and reliably
    present, not every rulebook-vs-real-world variant of this document.

    organization_name is anchored on "<ORG NAME> hereby authorizes 1LINK to
    take actions" (clause x), confirmed present in all 4 real samples so
    far. Deliberately case-sensitive: the org name is consistently ALL CAPS
    in this sentence, and a case-insensitive match pulls in unrelated
    lower-case prose ahead of it instead (confirmed while developing this
    pattern).

    No IBAN/account field, despite that being the department's stated
    focus: tested directly against real cached text before deciding.
    TMA_Lal_Dir_Upper's real sample has exactly one unambiguous IBAN;
    GDA_Abbotabad's real sample lists a 5-bank reference table with no
    textual indication of which one is operative -- the same ambiguity
    that already keeps branch_code (removed here) out of the critical set.
    RegexExtractor.extract() takes the first regex match unconditionally;
    it has no way to detect "more than one candidate exists" and fall back
    to honestly missing, so a plain IBAN pattern would silently return the
    wrong one of five real banks on that shape. Building the disambiguation
    needed to do this safely is exactly the kind of variant-by-variant
    validation this decision says to stop doing -- left out rather than
    added half-working.
    """

    document_type = AnalyzedDocumentType.ONE_LINK_LETTER

    _patterns = {
        "organization_name": re.compile(
            r"([A-Z][A-Z,.\s]{3,60}?)\s+hereby authorizes [1I]\s*LINK to take actions"
        ),
    }

    _post = {
        "organization_name": _as_single_line,
    }


class CnicFrontExtractor(RegexExtractor):
    """Extracts fields from a real Pakistani CNIC's front face.

    Front only -- DocumentType.CNIC_BACK has zero real samples anywhere in
    this session's cache (see CONTEXT.md), so back-face extraction is not
    attempted; a back upload still falls through to the generic ID_DOCUMENT
    classifier exactly as it did before this extractor existed.

    Built against 3 real cached samples (Confidential Data/.ocr_cache/,
    DG_Sports_KP_Onboarding_Documents__CNIC_FRONT_copy1/2/3.txt), all one
    organization -- real organizational diversity here is 1, not 3, stated
    honestly rather than implied. 2 of the 3 samples OCR'd with a clean,
    consistently ordered label-then-value layout (each label line immediately
    followed by its value line, or -- for adjacent label pairs like "Identity
    Number"/"Date of Birth" -- a label-block immediately followed by a
    value-block in the same order). The third sample OCR'd with the labels
    and values scrambled out of that order entirely (a genuinely different
    OCR read-order, not corrupted content -- copy2's contamination, documented
    separately in CONTEXT.md, is a distinct splitter merge-artifact bug, not
    this same issue). Every pattern below is anchored on the *clean* layout
    shape; on the scrambled sample a field either still happens to line up
    (document_number, full_name) or honestly misses (date_of_expiry) rather
    than risk pairing a label with the wrong value -- the same failure-
    avoidance principle as AMC's "/IBAN" garbage-capture lesson and 1-Link
    Letter's multi-bank-table miss.

    document_number is anchored purely on the canonical CNIC shape
    (5-7-1 digit groups, hyphen-separated) with no label dependency at all,
    so it is the one field that also extracts correctly on the scrambled
    sample -- confirmed against all 3 real samples. Deliberately named
    document_number, not cnic_number, to reuse
    app.rule_engine.rules.format_rules.FormatCnicRule's existing format
    validation (field_names=("document_number", "tax_reference_number")) for
    free, the same way branch_code was named to match CrossBranchCodeRule.

    full_name is anchored on a line that is exactly "Name" (not "Father
    Name", which the exact-line anchor deliberately excludes) followed by
    its value on the next line. Confirmed correct on all 3 real samples,
    including the scrambled one, where this specific label happened to still
    sit directly before its value despite everything else being out of
    order -- real evidence, not an assumption that the pattern generalizes.
    father_name was not attempted: the identical anchor shape only holds on
    2 of 3 samples for that label, and with only one real organization on
    file there isn't enough evidence yet to judge whether that is a real
    OCR-order pattern or coincidence.

    date_of_expiry is anchored on the exact two-line label block "Date of
    Issue" then "Date of Expiry" being immediately followed by a two-line
    value block, taking the second value as the expiry date. Confirmed
    correct on the 2 clean samples (both show a 10-year gap between the
    captured issue and expiry values, consistent with real CNIC validity
    periods -- a plausibility check, not proof, but supportive). Honestly
    misses on the scrambled sample, where this block shape does not occur
    intact. date_of_birth and date_of_issue were not attempted this pass to
    keep the first real-sample-validated version scoped to what
    docs/Master_Rules_Combined.md Section 12 actually asks for by name
    (format, expiry, readability, consistency) rather than extracting every
    field just because the layout partially allows it.
    """

    document_type = AnalyzedDocumentType.CNIC_FRONT

    _patterns = {
        "document_number": re.compile(r"\b(\d{5}-\d{7}-\d)\b"),
        "full_name": re.compile(r"(?m)^Name[ \t]*$\r?\n(.+)$"),
        "date_of_expiry": re.compile(
            r"(?m)^Date of Issue[ \t]*$\r?\n^Date of Expiry[ \t]*$\r?\n"
            r"[\d.]+[ \t]*\r?\n([\d.]+)"
        ),
    }

    _post = {
        "date_of_expiry": _as_iso_date_dotted,
    }


class FormalRequestLetterExtractor(RegexExtractor):
    """Extracts structured fields from a Formal Request Letter.

    Built against the one real sample on file (confirmed 2026-08-18, TMA Lal
    Dir Upper) -- previously absorbed silently into the ONE_LINK_LETTER
    group by the splitter (see splitter._STRONG_TITLE_PHRASES) since its
    real subject line ("REQUEST FOR DIGITAL ACCOUNT AND FOR ONLINE
    PAYMENTS") never matched the spec-guessed "FORMAL REQUEST LETTER"/
    "FORMAL REQUEST" phrases.

    organization_name originally captured only the office-holder title on
    the anchor's own line ("OFFICE OF THE <title>") instead of the real
    organization name one line below it; the pattern now explicitly
    discards the anchor's own line and captures the next one, which is
    where the one real sample states it. Not validated against any other
    anchor variant (DEPARTMENT OF/GOVERNMENT OF/TO THE/FROM) -- none has a
    real sample yet, so this shape is assumed to generalize, not confirmed.

    focal_person_designation previously bled across a line boundary: the
    bare word "Title" inside the real sample's "Account Title" table header
    (no colon) satisfied the old permissive `\\s*[:|-]?\\s*` gap, which
    happily crossed the newline into the next line's unrelated table
    content ("IBAN/Account No") and returned it as a designation. The
    pattern now requires an explicit `:`/`|`/`-` delimiter and keeps the
    surrounding whitespace on the same line, so a bare label-shaped
    substring with nothing after it can no longer match at all. This
    correctly leaves the field missing on the one real sample -- it never
    states a designation for its focal person -- an honest gap, not
    something this pattern should paper over.

    date is a known, still-open honest miss on the one real sample: the
    real text reads "Dated Dir(U) 13/07/2026" (unrelated words between the
    label and the date) and, separately, "Dated: 14-04-2026" referring to a
    third-party letter being cited, not this letter's own date -- neither
    fits this pattern's strict label-then-date shape, and matching the
    second would be actively wrong (the wrong letter's date). Not touched
    this pass.
    """

    document_type = AnalyzedDocumentType.FORMAL_REQUEST_LETTER

    _patterns = {
        "organization_name": re.compile(
            r"(?:OFFICE OF THE|DEPARTMENT OF|GOVERNMENT OF|TO THE|FROM[:|-]?)[^\n]*\n\s*(.+)",
            re.IGNORECASE,
        ),
        "addressee": re.compile(
            r"To,?\s*\n?\s*(The\s+Managing\s+Director[^\n,]*|Managing\s+Director[^\n,]*|KPITB[^\n,]*|Khyber\s+Pakhtunkhwa\s+Information\s+Technology\s+Board[^\n,]*)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "subject": re.compile(
            r"Subject\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "date": re.compile(
            r"(?:Date|Dated)\s*[:|-]?\s*([0-9]{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{2,4}|[0-9]{4}[/\-.][0-9]{1,2}[/\-.][0-9]{1,2}|\d{1,2}\s+[A-Za-z]+\s+\d{4})",
            re.IGNORECASE | re.MULTILINE,
        ),
        "focal_person_name": re.compile(
            r"(?:Focal Person Name|Focal Person|Contact Person|Authorized Representative|Submitted By|Signed By)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "focal_person_designation": re.compile(
            r"(?:Designation|Title)[ \t]*[:|-][ \t]*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
    }

    _post = {
        "date": _as_iso_date,
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
    AnalyzedDocumentType.FORMAL_REQUEST_LETTER: [
        ("formal request letter", 4),
        ("formal request", 3),
        ("request letter", 3),
        ("onboarding as a sub-biller", 3),
        ("managing director", 2),
        ("kpitb", 2),
        ("sub-biller", 2),
    ],
}

class AccountMaintenanceCertificateExtractor(RegexExtractor):
    """Extracts structured fields from an Account Maintenance Certificate.

    A bank certificate attesting an account's details: account title, account
    number, IBAN, issuing bank and branch. Field names deliberately mirror the
    cross-document consistency rules (``account_holder``, ``account_number``,
    ``iban``) so the normalization stage can compare them against the Bilateral
    and Tripartite agreements.

    account_holder/account_number/iban are produced by the structural
    ``_extract_bank_account_block`` parser rather than the label-anchored regex
    used elsewhere: the real cached layouts (Confidential Data/.ocr_cache/,
    four independent bank certificates) interleave label and value lines in
    shapes a single regex cannot capture without garbage-capture. Two concrete
    real bugs this fixes, both confirmed before the change: the combined
    ``Account No/IBAN`` label captured ``/IBAN`` as the account number, and a
    dotted-leader ``ACCOUNT NUMBER:...`` label failed its separator, so the
    account number leaked in from an unrelated certificate later in the file.
    """

    document_type = AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE

    _patterns = {
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

    def extract(self, text: str) -> dict[str, Any]:
        fields = super().extract(text)
        block = _extract_bank_account_block(text)
        for key in ("account_holder", "account_number", "iban"):
            if key not in fields and key in block:
                fields[key] = block[key]
        return fields


class TripartiteAgreementExtractor(RegexExtractor):
    """Extracts structured fields from a Tripartite Agreement.

    Captures the three named parties (1-Link, KPITB, the sub-biller) and the
    bank details section (account title, account number, branch) that must
    match the Account Maintenance Certificate. Field names follow the
    cross-document consistency rules (``account_holder``, ``account_number``,
    ``branch_code``).

    account_holder/account_number come from the structural
    ``_extract_bank_account_block`` parser: the one real sample validated
    (Confidential Data/.ocr_cache/) states the bank details as a stacked column
    table whose header block ("S# / Bank Name / IENT / Account Title / IBAN/
    Account No") is positionally mapped onto the value block. Before the change
    the greedy label-anchored regex captured the header ``IBAN/Account No`` as
    account_holder and the row index ``01`` as account_number -- confirmed
    garbage before fixing.
    """

    document_type = AnalyzedDocumentType.TRIPARTITE_AGREEMENT

    #: Patterns are label-anchored and deliberately tolerant of OCR noise:
    #: party names are captured up to the next comma, newline or the standard
    #: "(hereinafter referred to as ...)" clause. Tune against real samples.
    _patterns = {
        "party_1link": re.compile(
            r"((?:1\s*LINK|1-LINK|ONE[-\s]?LINK|ONELINK)[^,\n]*?)(?=\s*\(hereinafter|\s*,|\s*\n|$)",
            re.IGNORECASE,
        ),
        "party_kpitb": re.compile(
            r"((?:KHYBER PAKHTUNKHWA INFORMATION(?:\s*(?:&|AND))?\s*TECHNOLOGY BOARD|KPITB))(?=[\s,])",
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
            r"(?:Account Number|A/?C No\.?|Account No\.?)(?:\s*\(IBAN\))?\s*[:|-]?\s*(?:(?:[^A-Z0-9\n]*\n[^A-Z0-9\n]*.*?(?:\|[ \t]*)?)?([A-Z0-9]{10,30}))",
            re.IGNORECASE | re.MULTILINE,
        ),
        "branch_code": re.compile(
            r"(?:Branch Code|Branch)\s*:\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
    }

    def extract(self, text: str) -> dict[str, Any]:
        # Structural parser takes precedence (it correctly handles the stacked
        # column-table and interleaved label/value layouts seen in real cached
        # samples); the label-anchored patterns remain as a fallback for
        # layouts the structural parser does not recognize (e.g. pipe-separated
        # table rows). Structural results are never overwritten by a regex
        # match, so the pattern-based captures cannot re-introduce the garbage
        # values (headers, row indexes) the structural parser was written to
        # fix.
        fields = dict(_extract_bank_account_block(text))
        regex_fields = super().extract(text)
        for key in ("account_holder", "account_number"):
            if key not in fields and key in regex_fields:
                fields[key] = regex_fields[key]
        return fields


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
    AnalyzedDocumentType.ONE_LINK_LETTER: OneLinkLetterExtractor(),
    AnalyzedDocumentType.CNIC_FRONT: CnicFrontExtractor(),
    AnalyzedDocumentType.FORMAL_REQUEST_LETTER: FormalRequestLetterExtractor(),
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
