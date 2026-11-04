"""Duplicate transaction detection (exact and possible duplicates)."""

from __future__ import annotations

import difflib
from decimal import Decimal
from typing import Any, List


def detect_duplicates(
    transactions: List[dict[str, Any]],
    similarity_threshold: float = 0.85,
) -> dict[str, int]:
    """Identify exact and possible duplicate transactions and mark them.

    Rules:
        - exact_duplicate: same date, amount, direction, normalized description, and reference (if present)
        - possible_duplicate: same date, amount, direction, and description similarity >= similarity_threshold

    Never deletes any transaction. Sets duplicate_status ('exact_duplicate' | 'possible_duplicate')
    and duplicate_of (UUID of earlier transaction).

    Returns summary: {"exact": int, "possible": int}
    """
    summary = {"exact": 0, "possible": 0}
    n = len(transactions)

    for i in range(n):
        t1 = transactions[i]
        t1_date = t1.get("transaction_date")
        t1_debit = t1.get("debit")
        t1_credit = t1.get("credit")
        t1_desc = (t1.get("description") or "").lower().strip()
        t1_ref = t1.get("reference_number")

        for j in range(i + 1, n):
            t2 = transactions[j]
            # Already marked as duplicate of something earlier? continue
            if t2.get("duplicate_status") in ("exact_duplicate", "possible_duplicate"):
                continue

            t2_date = t2.get("transaction_date")
            t2_debit = t2.get("debit")
            t2_credit = t2.get("credit")
            t2_desc = (t2.get("description") or "").lower().strip()
            t2_ref = t2.get("reference_number")

            # Check matching date
            if t1_date != t2_date:
                continue

            # Check matching amount and direction
            debit_match = (t1_debit is not None and t2_debit is not None and t1_debit == t2_debit)
            credit_match = (t1_credit is not None and t2_credit is not None and t1_credit == t2_credit)

            if not (debit_match or credit_match):
                continue

            # Exact match check
            is_exact_desc = (t1_desc == t2_desc)
            ref_match = (t1_ref == t2_ref) if (t1_ref and t2_ref) else True

            if is_exact_desc and ref_match:
                t2["duplicate_status"] = "exact_duplicate"
                t2["duplicate_of"] = t1.get("id")
                summary["exact"] += 1
                continue

            # Possible duplicate check via difflib similarity
            matcher = difflib.SequenceMatcher(None, t1_desc, t2_desc)
            ratio = matcher.ratio()

            if ratio >= similarity_threshold:
                t2["duplicate_status"] = "possible_duplicate"
                t2["duplicate_of"] = t1.get("id")
                t2["needs_review"] = True
                summary["possible"] += 1

    return summary

