"""
Field Extraction Module.

Uses Regex and text processing rules to extract structured fields
(like CNIC, IBAN, Account Numbers) from raw OCR text.
"""

import re
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class FieldExtractor:
    def __init__(self):
        # Compiled Regex Patterns
        self.patterns = {
            "cnic": re.compile(r'\b\d{5}[-\s]?\d{7}[-\s]?\d{1}\b'),
            "iban": re.compile(r'\bPK\d{2}[A-Z]{4}\d{16}\b', re.IGNORECASE),
            # General account number heuristic: 10-24 digits possibly separated by dashes
            "account_number": re.compile(r'\b\d{4,6}[-\s]?\d{4,10}[-\s]?\d{2,6}\b'),
            # Date heuristc: DD-MM-YYYY, DD/MM/YYYY, etc.
            "date": re.compile(r'\b\d{2}[-/]\d{2}[-/]\d{4}\b'),
            "ntn": re.compile(r'\b\d{7}[-\s]?\d{1}\b')
        }

    def extract_cnic(self, text: str) -> Optional[str]:
        """Extract Pakistani CNIC from text."""
        match = self.patterns["cnic"].search(text)
        if match:
            # Normalize to XXXXX-XXXXXXX-X format
            clean_cnic = re.sub(r'[^\d]', '', match.group())
            if len(clean_cnic) == 13:
                return f"{clean_cnic[:5]}-{clean_cnic[5:12]}-{clean_cnic[12]}"
        return None

    def extract_iban(self, text: str) -> Optional[str]:
        """Extract Pakistani IBAN from text."""
        # Strip all whitespace for IBAN matching first
        compact_text = re.sub(r'\s+', '', text)
        match = self.patterns["iban"].search(compact_text)
        if match:
            return match.group().upper()
        return None

    def find_keyword_context(self, text: str, keyword: str, window: int = 50) -> Optional[str]:
        """
        Find a keyword (case insensitive) and return surrounding text.
        Useful for extracting Account Titles near 'Title of Account'.
        """
        match = re.search(r'\b' + re.escape(keyword) + r'\b', text, re.IGNORECASE)
        if match:
            start = max(0, match.end())
            end = min(len(text), start + window)
            return text[start:end].strip()
        return None

    def has_keyword(self, text: str, keyword: str) -> bool:
        """Simple boolean check for keyword presence."""
        return bool(re.search(r'\b' + re.escape(keyword) + r'\b', text, re.IGNORECASE))
