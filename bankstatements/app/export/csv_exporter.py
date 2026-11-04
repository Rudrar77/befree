"""CSV export with formula injection protection."""

from __future__ import annotations

import csv
import io
from typing import Any, List


def sanitize_for_csv(value: Any) -> str:
    """Sanitize string to prevent formula injection in Excel / spreadsheets.

    Prefix with single quote (') if string begins with =, +, -, @, tab, or carriage return.
    """
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


def export_transactions_to_csv(transactions: List[Any]) -> io.BytesIO:
    """Export transactions to CSV format per Appendix A5.

    Columns:
        Transaction Date, Description, Debit, Credit, Balance, Category,
        Classification Method, Confidence Score, Validation Status
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    headers = [
        "Transaction Date",
        "Description",
        "Debit",
        "Credit",
        "Balance",
        "Category",
        "Classification Method",
        "Confidence Score",
        "Validation Status",
    ]
    writer.writerow(headers)

    for t in transactions:
        t_date = t.transaction_date.isoformat() if hasattr(t, "transaction_date") and t.transaction_date else ""
        desc = t.description if hasattr(t, "description") else t.get("description", "")
        debit = f"{t.debit:.2f}" if hasattr(t, "debit") and t.debit is not None else ""
        credit = f"{t.credit:.2f}" if hasattr(t, "credit") and t.credit is not None else ""
        balance = f"{t.balance:.2f}" if hasattr(t, "balance") and t.balance is not None else ""
        category = t.category_name if hasattr(t, "category_name") else t.get("category_name", "Uncategorized")
        method = t.classification_method if hasattr(t, "classification_method") else t.get("classification_method", "none")
        confidence = f"{t.confidence:.2f}" if hasattr(t, "confidence") and t.confidence is not None else ""
        val_status = t.validation_status if hasattr(t, "validation_status") else t.get("validation_status", "valid")

        writer.writerow([
            sanitize_for_csv(t_date),
            sanitize_for_csv(desc),
            debit,
            credit,
            balance,
            sanitize_for_csv(category),
            sanitize_for_csv(method),
            confidence,
            sanitize_for_csv(val_status),
        ])

    bytes_out = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    bytes_out.seek(0)
    return bytes_out

