"""Abstract base class for Bank Parsers."""

from __future__ import annotations

import abc
from typing import Any, List, Optional


class BankParser(abc.ABC):
    """Abstract base class for bank-specific statement parsers."""

    @property
    @abc.abstractmethod
    def bank_name(self) -> str:
        """Name of the bank (e.g. 'State Bank of India', 'HDFC Bank')."""
        pass

    @property
    @abc.abstractmethod
    def ifsc_prefix(self) -> Optional[str]:
        """Expected IFSC prefix (e.g. 'SBIN', 'HDFC')."""
        pass

    @abc.abstractmethod
    def detect(self, text: str) -> float:
        """Compute confidence score [0.0 - 1.0] that this statement belongs to this bank.

        Args:
            text: Initial statement text (e.g., first 1-2 pages)

        Returns:
            Float confidence score between 0.0 and 1.0
        """
        pass

    @abc.abstractmethod
    def parse_account_info(self, text: str) -> dict[str, Any]:
        """Extract statement-level account details.

        Returns dictionary with keys:
            - account_holder_name: str | None
            - account_number_masked: str | None (always masked!)
            - ifsc: str | None
            - branch_name: str | None
            - period_start: date | None
            - period_end: date | None
            - opening_balance: Decimal | None
            - closing_balance: Decimal | None
        """
        pass

    @abc.abstractmethod
    def parse_transactions(
        self,
        pages_content: List[dict[str, Any]],
    ) -> tuple[List[dict[str, Any]], List[dict[str, Any]]]:
        """Extract transactions from all pages.

        Args:
            pages_content: List of per-page data containing 'page_num', 'text', 'tables', 'rows'

        Returns:
            Tuple of:
            - transactions: list of raw transaction dicts
            - unresolved_rows: list of raw unresolved dicts
        """
        pass

