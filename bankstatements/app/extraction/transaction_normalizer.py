"""Transaction extraction and normalization engine."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, List, Optional, Tuple

DATE_PATTERNS = [
    (re.compile(r"^\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b"), "%d/%m/%Y"),
    (re.compile(r"^\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2})\b"), "%d/%m/%y"),
    (re.compile(r"^\b(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})\b"), "%Y-%m-%d"),
    (re.compile(r"^\b(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\b"), "%d %b %Y"),
    (re.compile(r"^\b(\d{1,2})-([A-Za-z]{3})-(\d{4})\b"), "%d-%b-%Y"),
    (re.compile(r"^\b(\d{1,2})-([A-Za-z]{3})-(\d{2})\b"), "%d-%b-%y"),
    (re.compile(r"^\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b"), "%b %d %Y"),
]

# Robust patterns for references requiring numeric or alphanumeric identifiers
UPI_REF_REGEX = re.compile(r"\bUPI(?:/CR|/DR)?[/: ]*(?:[A-Za-z0-9_-]+[/: ])*([0-9]{8,18})\b", re.IGNORECASE)
NEFT_REF_REGEX = re.compile(r"\bNEFT[/: -]*([0-9A-Za-z]{6,20})\b", re.IGNORECASE)
IMPS_REF_REGEX = re.compile(r"\bIMPS(?:/(?:P2A|P2U|P2P))?[/: -]*([0-9A-Za-z]{6,20})\b", re.IGNORECASE)
CHEQUE_REF_REGEX = re.compile(r"\b(?:CHQ|CHEQUE|CHQ NO)[/: -]*([0-9]{4,10})\b", re.IGNORECASE)
GENERIC_REF_REGEX = re.compile(r"\b(?:REF|UTR|TXN)[/: #]*([0-9A-Za-z]{6,20})\b", re.IGNORECASE)


def parse_date(date_str: str) -> Optional[date]:
    """Parse various bank date formats into a standard date object."""
    if not date_str:
        return None
    cleaned = date_str.strip()

    for pattern, fmt in DATE_PATTERNS:
        match = pattern.match(cleaned)
        if match:
            matched_str = match.group(0).replace(".", "/").replace("-", "/")
            if fmt == "%d %b %Y" or fmt == "%d-%b-%Y":
                try:
                    return datetime.strptime(match.group(0), fmt).date()
                except ValueError:
                    pass
            elif fmt == "%b %d %Y":
                try:
                    s_clean = match.group(0).replace(",", "")
                    parts = s_clean.split()
                    m_str = parts[0][:3]
                    return datetime.strptime(f"{m_str} {parts[1]} {parts[2]}", "%b %d %Y").date()
                except ValueError:
                    pass
            elif fmt == "%d-%b-%y":
                try:
                    return datetime.strptime(match.group(0), fmt).date()
                except ValueError:
                    pass
            else:
                try:
                    if fmt == "%d/%m/%Y":
                        return datetime.strptime(matched_str, "%d/%m/%Y").date()
                    elif fmt == "%d/%m/%y":
                        return datetime.strptime(matched_str, "%d/%m/%y").date()
                    elif fmt == "%Y-%m-%d":
                        return datetime.strptime(matched_str.replace("/", "-"), "%Y-%m-%d").date()
                except ValueError:
                    pass

    return None


def parse_money(amount_str: Any) -> Optional[Decimal]:
    """Parse Indian or international money strings into Decimal.

    Handles:
        - Indian grouping: '1,23,456.78'
        - Western grouping: '123,456.78'
        - Multi-currency: '₹', '$', '€', '£', 'AED', 'USD', 'EUR', 'GBP', etc.
        - Trailing/leading Cr/Dr: '500.00 Cr', 'Dr 100.00', '300.00 (Dr)'
        - Parentheses/negatives: '(500.00)', '-1,234.50'
    """
    if amount_str is None:
        return None
    if isinstance(amount_str, (int, float, Decimal)):
        return Decimal(str(amount_str)).quantize(Decimal("0.01"))

    s = str(amount_str).strip()
    if not s or s in ("-", "--", "—", "N/A", "null", "none"):
        return None

    # Check for accounting parentheses negative e.g. (500.00) vs (Dr)/(Cr) suffix
    has_dr_cr_paren = bool(re.search(r"(?i)\((?:cr|dr)\)", s))
    is_paren_negative = False
    if not has_dr_cr_paren and s.startswith("(") and s.endswith(")"):
        is_paren_negative = True
        s = s[1:-1].strip()

    # Strip currency symbols and names
    s = re.sub(r"(?i)\b(USD|EUR|GBP|AED|CAD|AUD|SGD|CHF|INR|RS|RS\.)\b", "", s)
    s = re.sub(r"[\$€£₹¥]", "", s).strip()

    # Strip Dr / Cr suffixes
    s = re.sub(r"(?i)\((?:cr|dr)\)|\b(cr|dr)\b", "", s).strip()
    s = s.replace(",", "")
    s = re.sub(r"[^\d.-]", "", s)
    if not s or s in ("-", ".", "-.", ".-"):
        return None

    try:
        val = Decimal(s)
        if is_paren_negative and val > 0:
            val = -val
        return val.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def extract_reference_number(description: str) -> Optional[str]:
    """Extract payment reference number (UPI / NEFT / IMPS / Cheque / UTR) from description."""
    if not description:
        return None

    for regex in (UPI_REF_REGEX, NEFT_REF_REGEX, IMPS_REF_REGEX, CHEQUE_REF_REGEX, GENERIC_REF_REGEX):
        m = regex.search(description)
        if m:
            ref = m.group(1).strip()
            if len(ref) >= 4:
                return ref

    return None


def normalize_description(raw: str) -> str:
    """Clean and normalize a transaction description string."""
    if not raw:
        return ""
    cleaned = re.sub(r"\s+", " ", raw).strip()
    return cleaned


def is_balance_metadata_row(
    raw_desc: Optional[str],
    raw_text: Optional[str],
    debit: Optional[Decimal],
    credit: Optional[Decimal],
    balance: Optional[Decimal],
) -> bool:
    """Ignore rows that describe opening/closing balances rather than transactions."""
    haystack = f"{raw_desc or ''} {raw_text or ''}".lower()
    if not haystack:
        return False
    if not re.search(
        r"\b(?:opening\s*(?:balance)?|open\s*bal|balance\s*forward|brought\s*forward|b/f|closing\s*(?:balance)?|close\s*bal|carried\s*forward|c/f)\b",
        haystack,
    ):
        return False
    return (debit is None and credit is None) or balance is not None


def normalize_transactions(
    raw_rows: List[dict[str, Any]],
    statement_id: str,
    opening_balance: Optional[Decimal] = None,
) -> Tuple[List[dict[str, Any]], List[dict[str, Any]]]:
    """Normalize extracted transaction rows into strict schema representations."""
    normalized_list: List[dict[str, Any]] = []
    unresolved_list: List[dict[str, Any]] = []

    running_prev_balance = opening_balance

    for i, row in enumerate(raw_rows):
        source_page = row.get("source_page", 1)
        raw_text = row.get("raw_text") or str(row)
        extraction_method = row.get("extraction_method", "text")

        raw_date = row.get("date")
        parsed_date = parse_date(raw_date) if raw_date else None

        raw_desc = row.get("description", "")
        debit_val = parse_money(row.get("debit"))
        credit_val = parse_money(row.get("credit"))
        balance_val = parse_money(row.get("balance"))
        single_amount = parse_money(row.get("amount"))

        if is_balance_metadata_row(raw_desc, raw_text, debit_val, credit_val, balance_val):
            continue

        # Multi-line continuation: no date, no amount, previous transaction exists
        if (
            not parsed_date
            and debit_val is None
            and credit_val is None
            and single_amount is None
            and raw_desc
            and normalized_list
            and not row.get("reference_number")
        ):
            prev = normalized_list[-1]
            prev["description"] = normalize_description(prev["description"] + " " + raw_desc)
            prev["original_description"] = prev["original_description"] + "\n" + raw_desc
            # Extract or update reference number from continuation
            continuation_ref = extract_reference_number(raw_desc)
            if continuation_ref:
                prev["reference_number"] = continuation_ref
            elif not prev.get("reference_number"):
                prev["reference_number"] = extract_reference_number(prev["description"])
            continue

        warnings: List[str] = list(row.get("warnings") or [])
        is_ambiguous = False
        type_str = str(row.get("type", "")).upper()

        if single_amount is not None and debit_val is None and credit_val is None:
            if "CR" in type_str or "CREDIT" in type_str:
                credit_val = abs(single_amount)
            elif "DR" in type_str or "DEBIT" in type_str or single_amount < 0:
                debit_val = abs(single_amount)
            elif balance_val is not None and running_prev_balance is not None:
                diff = balance_val - running_prev_balance
                if abs(diff) == abs(single_amount):
                    if diff > Decimal("0"):
                        credit_val = abs(single_amount)
                    elif diff < Decimal("0"):
                        debit_val = abs(single_amount)
                if debit_val is None and credit_val is None:
                    warnings.append(
                        "Amount direction is uncertain; extracted amount was retained for review."
                    )
                    is_ambiguous = True
            elif single_amount > 0 and type_str == "":
                warnings.append(
                    "Amount direction is uncertain; extracted amount was retained for review."
                )
                is_ambiguous = True
            else:
                warnings.append(
                    "Amount direction is uncertain; extracted amount was retained for review."
                )
                is_ambiguous = True

        if debit_val is not None and credit_val is not None:
            warnings.append("Row contains both debit and credit amounts")
            is_ambiguous = True

        if debit_val is not None:
            debit_val = abs(debit_val)
        if credit_val is not None:
            credit_val = abs(credit_val)

        if (
            parsed_date is None
            and debit_val is None
            and credit_val is None
            and not raw_desc
            and not row.get("reference_number")
        ):
            unresolved_list.append({
                "id": str(uuid.uuid4()),
                "statement_id": statement_id,
                "source_page": source_page,
                "raw_text": raw_text,
                "reason": "Empty or unparseable row",
                "extraction_method": extraction_method,
            })
            continue

        if parsed_date is None:
            warnings.append("Missing transaction date")
            is_ambiguous = True

        if not raw_desc:
            warnings.append("Missing transaction description")

        norm_desc = normalize_description(raw_desc)
        ref_num = row.get("reference_number") or extract_reference_number(norm_desc)

        if balance_val is not None:
            running_prev_balance = balance_val
        elif running_prev_balance is not None:
            if credit_val:
                running_prev_balance += credit_val
            elif debit_val:
                running_prev_balance -= debit_val

        txn_record = {
            "id": str(uuid.uuid4()),
            "transaction_id": row.get("transaction_id"),
            "statement_id": statement_id,
            "transaction_date": parsed_date,
            "description": norm_desc,
            "original_description": raw_desc,
            "debit": debit_val,
            "credit": credit_val,
            "balance": balance_val,
            "reference_number": ref_num,
            "category_id": None,
            "classification_method": "none",
            "confidence": None,
            "applied_rule_id": None,
            "model_version": None,
            "manual_override": False,
            "needs_review": is_ambiguous or bool(warnings),
            "duplicate_status": "none",
            "duplicate_of": None,
            "validation_status": "warning" if warnings else "valid",
            "review_status": "NEEDS REVIEW" if warnings or is_ambiguous else "PASS",
            "anomaly_flags": [],
            "source_page": source_page,
            "source_row": row.get("source_row", i + 1),
            "mode": row.get("mode") or None,
            "currency": row.get("currency") or "INR",
            "original_amount_text": row.get("amount") or row.get("debit") or row.get("credit") or None,
            "extraction_confidence": row.get("extraction_confidence"),
            "extraction_method": extraction_method,
            "warnings": warnings,
            "notes": None,
        }

        normalized_list.append(txn_record)

    return normalized_list, unresolved_list
