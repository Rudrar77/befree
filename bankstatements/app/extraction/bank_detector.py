"""Parser selection and display-name detection for bank statements."""

from __future__ import annotations

import re
from typing import Tuple

from app.extraction.bank_parser import BankParser
from app.extraction.parsers.registry import get_generic_parser

IFSC_REGEX = re.compile(r"\b([A-Z]{4})0([A-Z0-9]{6})\b", re.IGNORECASE)

BANK_IFSC_MAP = {
    "SBIN": "State Bank of India",
    "HDFC": "HDFC Bank",
    "ICIC": "ICICI Bank",
    "UTIB": "Axis Bank",
    "BARB": "Bank of Baroda",
    "KKBK": "Kotak Mahindra Bank",
    "UCBA": "UCO Bank",
    "UBIN": "Union Bank of India",
}

BANK_NAME_MARKERS = {
    "State Bank of India": ("state bank of india",),
    "HDFC Bank": ("hdfc bank",),
    "ICICI Bank": ("icici bank",),
    "Axis Bank": ("axis bank",),
    "Bank of Baroda": ("bank of baroda",),
    "Kotak Mahindra Bank": ("kotak mahindra bank", "kotak bank"),
    "UCO Bank": ("uco bank",),
    "Union Bank of India": ("union bank of india", "union bank"),
}


def detect_bank_name(text: str) -> str | None:
    """Infer a display bank name without selecting a bank-specific parser."""
    match = re.search(
        r"\bIFSC(?:[ \t]+CODE)?[ \t]*[:.]?[ \t]*([A-Z]{4}0[A-Z0-9]{6})\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        label = re.search(r"\bIFSC(?:\s+CODE)?\b", text, re.IGNORECASE)
        if label:
            match = re.search(
                r"\b([A-Z]{4}0[A-Z0-9]{6})\b",
                text[label.end():label.end() + 500],
                re.IGNORECASE,
            )
    if match:
        bank_name = BANK_IFSC_MAP.get(match.group(1)[:4].upper())
        if bank_name:
            return bank_name

    text_lower = text.lower()
    for bank_name, markers in BANK_NAME_MARKERS.items():
        if any(marker in text_lower for marker in markers):
            return bank_name

    match = IFSC_REGEX.search(text)
    return BANK_IFSC_MAP.get(match.group(1).upper()) if match else None


def detect_bank(
    text: str,
    confidence_threshold: float = 0.4,
) -> Tuple[BankParser, float]:
    """Return the shared generic parser for every statement.

    The arguments remain for compatibility with existing callers; parser
    selection no longer varies by bank.
    """
    return get_generic_parser(), 0.0
