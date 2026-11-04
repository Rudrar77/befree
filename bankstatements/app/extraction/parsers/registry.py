"""Parser registry exposing the shared generic statement parser."""

from __future__ import annotations

from typing import List
from app.extraction.bank_parser import BankParser
from app.extraction.parsers.generic import GenericParser

_GENERIC_PARSER: GenericParser = GenericParser()


def get_generic_parser() -> GenericParser:
    """Return singleton instance of GenericParser."""
    return _GENERIC_PARSER


def discover_parsers() -> List[BankParser]:
    """Return the generic parser as the only supported parser."""
    return [_GENERIC_PARSER]


def get_all_parsers() -> List[BankParser]:
    """Return the available parser for backward compatibility."""
    return discover_parsers()
