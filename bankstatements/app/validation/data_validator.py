"""Data validation checks on extracted statement transactions."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Any, List, Optional

from app.extraction.transaction_normalizer import parse_date

IFSC_REGEX = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def _coerce_date(value: Any) -> Optional[date]:
    """Convert serialized or native date values to a comparable date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return parse_date(value)
    return None


def validate_statement_data(
    statement_info: dict[str, Any],
    transactions: List[dict[str, Any]],
    unresolved_rows: List[dict[str, Any]],
) -> List[dict[str, Any]]:
    """Run data integrity validation checks on statement metadata and transactions.

    Returns:
        List of validation issue dicts:
        [{
            "id": uuid,
            "statement_id": str,
            "severity": "warning" | "error",
            "code": str,
            "message": str,
            "transaction_id": str | None,
            "transaction_description": str | None
        }]
    """
    issues: List[dict[str, Any]] = []
    statement_id = statement_info.get("id", "")

    # 1. Statement-level validations
    ifsc = statement_info.get("ifsc")
    if ifsc and not IFSC_REGEX.match(ifsc.upper()):
        issues.append({
            "id": str(uuid.uuid4()),
            "statement_id": statement_id,
            "severity": "warning",
            "code": "MALFORMED_IFSC",
            "message": f"IFSC code '{ifsc}' does not follow the standard 11-character format.",
            "transaction_id": None,
            "transaction_description": None,
        })

    period_start = _coerce_date(statement_info.get("period_start"))
    period_end = _coerce_date(statement_info.get("period_end"))
    if period_start and period_end and period_start > period_end:
        issues.append({
            "id": str(uuid.uuid4()),
            "statement_id": statement_id,
            "severity": "error",
            "code": "INVALID_PERIOD",
            "message": f"Statement period start ({period_start}) is after period end ({period_end}).",
            "transaction_id": None,
            "transaction_description": None,
        })

    if unresolved_rows:
        issues.append({
            "id": str(uuid.uuid4()),
            "statement_id": statement_id,
            "severity": "warning",
            "code": "UNRESOLVED_ROWS_PRESENT",
            "message": f"{len(unresolved_rows)} row(s) could not be parsed into transactions.",
            "transaction_id": None,
            "transaction_description": None,
        })

    # 2. Transaction-level validations
    for txn in transactions:
        t_id = txn.get("id")
        t_desc = txn.get("description", "")
        t_date = _coerce_date(txn.get("transaction_date"))
        debit = txn.get("debit")
        credit = txn.get("credit")
        balance = txn.get("balance")

        # Missing / invalid date
        if not t_date:
            issues.append({
                "id": str(uuid.uuid4()),
                "statement_id": statement_id,
                "severity": "error",
                "code": "MISSING_DATE",
                "message": "Transaction date is missing or invalid.",
                "transaction_id": t_id,
                "transaction_description": t_desc,
            })
            txn["validation_status"] = "error"
        elif period_start and period_end:
            if t_date < period_start or t_date > period_end:
                issues.append({
                    "id": str(uuid.uuid4()),
                    "statement_id": statement_id,
                    "severity": "warning",
                    "code": "OUTSIDE_STATEMENT_PERIOD",
                    "message": f"Transaction date {t_date} is outside the statement period ({period_start} to {period_end}).",
                    "transaction_id": t_id,
                    "transaction_description": t_desc,
                })
                if txn.get("validation_status") != "error":
                    txn["validation_status"] = "warning"

        # Missing description
        if not t_desc or t_desc == "Unspecified Transaction":
            issues.append({
                "id": str(uuid.uuid4()),
                "statement_id": statement_id,
                "severity": "warning",
                "code": "MISSING_DESCRIPTION",
                "message": "Transaction description is empty or missing.",
                "transaction_id": t_id,
                "transaction_description": t_desc,
            })
            if txn.get("validation_status") != "error":
                txn["validation_status"] = "warning"

        # Amount validation: both debit and credit
        if debit is not None and credit is not None:
            issues.append({
                "id": str(uuid.uuid4()),
                "statement_id": statement_id,
                "severity": "error",
                "code": "BOTH_DEBIT_AND_CREDIT",
                "message": "Transaction has both debit and credit amounts.",
                "transaction_id": t_id,
                "transaction_description": t_desc,
            })
            txn["validation_status"] = "error"

        # Amount validation: neither debit nor credit
        if debit is None and credit is None:
            issues.append({
                "id": str(uuid.uuid4()),
                "statement_id": statement_id,
                "severity": "error",
                "code": "MISSING_AMOUNT",
                "message": "Transaction has neither debit nor credit amount.",
                "transaction_id": t_id,
                "transaction_description": t_desc,
            })
            txn["validation_status"] = "error"

        # Negative amount check
        if (debit is not None and debit < 0) or (credit is not None and credit < 0):
            issues.append({
                "id": str(uuid.uuid4()),
                "statement_id": statement_id,
                "severity": "error",
                "code": "NEGATIVE_AMOUNT",
                "message": "Debit or credit amount is negative (must be positive, sign is carried by direction).",
                "transaction_id": t_id,
                "transaction_description": t_desc,
            })
            txn["validation_status"] = "error"

        # Missing balance
        if balance is None:
            issues.append({
                "id": str(uuid.uuid4()),
                "statement_id": statement_id,
                "severity": "warning",
                "code": "MISSING_BALANCE",
                "message": "Running balance is not recorded for this transaction.",
                "transaction_id": t_id,
                "transaction_description": t_desc,
            })
            if txn.get("validation_status") != "error":
                txn["validation_status"] = "warning"

    return issues
