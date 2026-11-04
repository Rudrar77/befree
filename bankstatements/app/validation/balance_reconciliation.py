"""Balance reconciliation and running balance verification."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional, Tuple


def reconcile_statement_balances(
    opening_balance: Optional[Decimal],
    closing_balance: Optional[Decimal],
    transactions: List[dict[str, Any]],
    tolerance: Decimal = Decimal("0.01"),
) -> dict[str, Any]:
    """Reconcile statement balances against transactions.

    Formula: expected_closing = opening_balance + sum(credits) - sum(debits)
    Statuses:
        - matched: expected == closing within tolerance
        - mismatch: difference > tolerance
        - not_possible: opening or closing balance missing

    Also verifies running balances across transactions and identifies the first break.

    Returns dict matching Appendix A4 reconciliation shape:
        {
            "status": "matched" | "mismatch" | "not_possible",
            "opening_balance": str | None,
            "total_credits": str,
            "total_debits": str,
            "expected_closing_balance": str | None,
            "actual_closing_balance": str | None,
            "difference": str | None,
            "tolerance": str,
            "notes": list[str]
        }
    """
    notes: List[str] = []
    incomplete_reasons: List[str] = []

    # Calculate total credits and debits using Decimal
    total_credits = Decimal("0.00")
    total_debits = Decimal("0.00")

    for t in transactions:
        if t.get("credit") is None and t.get("debit") is None:
            incomplete_reasons.append("One or more transaction credit/debit fields are missing.")
        if t.get("credit") is not None:
            total_credits += Decimal(str(t["credit"]))
        if t.get("debit") is not None:
            total_debits += Decimal(str(t["debit"]))

    total_credits = total_credits.quantize(Decimal("0.01"))
    total_debits = total_debits.quantize(Decimal("0.01"))

    # Check if reconciliation is possible
    if opening_balance is None or closing_balance is None:
        if opening_balance is None and closing_balance is None:
            notes.append("Neither opening nor closing balance found in statement.")
        elif opening_balance is None:
            notes.append("Opening balance not found in statement header.")
        else:
            notes.append("Closing balance not found in statement.")

        return {
            "status": "not_possible",
            "validation_status": "INCOMPLETE",
            "reconciliation_status": "INCOMPLETE",
            "first_mismatch": None,
            "opening_balance": f"{opening_balance:.2f}" if opening_balance is not None else None,
            "total_credits": f"{total_credits:.2f}",
            "total_debits": f"{total_debits:.2f}",
            "expected_closing_balance": None,
            "actual_closing_balance": f"{closing_balance:.2f}" if closing_balance is not None else None,
            "difference": None,
            "tolerance": str(tolerance),
            "notes": notes,
        }

    expected_closing = (opening_balance + total_credits - total_debits).quantize(Decimal("0.01"))
    difference = (closing_balance - expected_closing).quantize(Decimal("0.01"))
    abs_diff = abs(difference)

    is_matched = abs_diff <= tolerance
    status = "matched" if is_matched else "mismatch"
    first_mismatch: dict[str, Any] | None = None

    if is_matched:
        notes.append("Statement balances reconcile successfully within tolerance.")
    else:
        notes.append(
            f"Balance mismatch: Expected {expected_closing:.2f}, but actual closing is {closing_balance:.2f} (diff: {difference:.2f})."
        )

    def transaction_date(txn: dict[str, Any]) -> date:
        value = txn.get("transaction_date")
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return date.min
        return date.min

    ordered_transactions = list(transactions)
    if len(ordered_transactions) > 1:
        first_date = transaction_date(ordered_transactions[0])
        last_date = transaction_date(ordered_transactions[-1])
        if first_date > last_date:
            ordered_transactions.reverse()
            notes.append(
                "Transactions detected in newest-first order; verified in chronological sequence."
            )
        elif first_date == date.min or last_date == date.min:
            ordered_transactions.sort(key=transaction_date)

    current_expected = opening_balance
    for txn in ordered_transactions:
        debit_value = txn.get("debit")
        credit_value = txn.get("credit")
        balance_value = txn.get("balance")
        if debit_value is None and credit_value is None:
            if "One or more transaction credit/debit fields are missing." not in incomplete_reasons:
                incomplete_reasons.append("One or more transaction credit/debit fields are missing.")
            continue
        debit = Decimal(str(debit_value or "0.00"))
        credit = Decimal(str(credit_value or "0.00"))
        current_expected = (current_expected + credit - debit).quantize(Decimal("0.01"))
        if balance_value is None:
            if "One or more transaction running balances are missing." not in incomplete_reasons:
                incomplete_reasons.append("One or more transaction running balances are missing.")
            continue
        reported_balance = Decimal(str(balance_value))
        if abs(reported_balance - current_expected) > tolerance and first_mismatch is None:
            first_mismatch = {
                "transaction_id": txn.get("id"),
                "source_page": txn.get("source_page"),
                "source_row": txn.get("source_row"),
                "description": str(txn.get("description", ""))[:80],
                "expected_balance": f"{current_expected:.2f}",
                "reported_balance": f"{reported_balance:.2f}",
            }
            notes.append(
                f"Running balance mismatch at transaction '{first_mismatch['description']}': "
                f"reported {reported_balance:.2f}, expected {current_expected:.2f}."
            )

    if incomplete_reasons:
        notes.extend(reason for reason in dict.fromkeys(incomplete_reasons) if reason not in notes)
    if first_mismatch is not None:
        validation_status = "MISMATCH"
    elif not is_matched:
        validation_status = "MISMATCH"
    elif incomplete_reasons:
        validation_status = "INCOMPLETE"
    elif any(txn.get("needs_review") for txn in transactions):
        validation_status = "NEEDS REVIEW"
        notes.append("One or more transactions require manual review.")
    else:
        validation_status = "PASS"

    if validation_status == "MISMATCH":
        status = "mismatch"
    elif validation_status in {"INCOMPLETE", "NEEDS REVIEW"}:
        status = "not_possible"
    else:
        status = "matched"

    return {
        "status": status,
        "validation_status": validation_status,
        "reconciliation_status": validation_status,
        "first_mismatch": first_mismatch,
        "opening_balance": f"{opening_balance:.2f}",
        "total_credits": f"{total_credits:.2f}",
        "total_debits": f"{total_debits:.2f}",
        "expected_closing_balance": f"{expected_closing:.2f}",
        "actual_closing_balance": f"{closing_balance:.2f}",
        "difference": f"{difference:.2f}",
        "tolerance": str(tolerance),
        "notes": notes,
    }
