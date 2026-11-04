"""Financial analytics calculation matching Appendix A4."""

from __future__ import annotations

import collections
from datetime import date
from decimal import Decimal
from typing import Any, List, Optional


def compute_financial_analytics(
    transactions: List[Any],
    scope: str = "statement",
    statement_id: Optional[str] = None,
    transfer_category_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Calculate financial analytics per Appendix A4.

    Rules:
    - Transfers (is_transfer=True) are EXCLUDED from income/expenses and reported only in transfers_in/transfers_out.
    - All money figures are 2-decimal strings.
    - Empty dataset -> null / empty arrays, not fake zeros for averages.
    """
    if transfer_category_ids is None:
        transfer_category_ids = set()

    total_income = Decimal("0.00")
    total_expenses = Decimal("0.00")
    transfers_in = Decimal("0.00")
    transfers_out = Decimal("0.00")

    debit_count = 0
    credit_count = 0
    debit_total = Decimal("0.00")
    credit_total = Decimal("0.00")

    all_amounts: List[Decimal] = []

    highest_debit: Optional[dict[str, Any]] = None
    max_debit_amt = Decimal("0.00")

    highest_credit: Optional[dict[str, Any]] = None
    max_credit_amt = Decimal("0.00")

    category_sums = collections.defaultdict(
        lambda: {"total": Decimal("0.00"), "count": 0, "name": "", "color": None}
    )
    monthly_data = collections.defaultdict(lambda: {"income": Decimal("0.00"), "expenses": Decimal("0.00")})
    daily_counts = collections.defaultdict(int)

    unclassified_count = 0

    for t in transactions:
        t_id = t.id if hasattr(t, "id") else t.get("id")
        t_desc = t.description if hasattr(t, "description") else t.get("description", "")
        t_date = t.transaction_date if hasattr(t, "transaction_date") else t.get("transaction_date")
        date_str = t_date.isoformat() if t_date else None

        debit_val = t.debit if hasattr(t, "debit") else t.get("debit")
        credit_val = t.credit if hasattr(t, "credit") else t.get("credit")

        debit = Decimal(str(debit_val)) if debit_val is not None else None
        credit = Decimal(str(credit_val)) if credit_val is not None else None

        cat_id = t.category_id if hasattr(t, "category_id") else t.get("category_id")
        cat_name = t.category_name if hasattr(t, "category_name") else t.get("category_name", "Uncategorized")
        category = getattr(t, "category", None)
        cat_color = (
            category.color
            if category
            else t.get("category_color") if isinstance(t, dict) else None
        )
        is_transfer = cat_id in transfer_category_ids or cat_name.lower() == "transfers"

        # Check unclassified
        method = t.classification_method if hasattr(t, "classification_method") else t.get("classification_method")
        needs_review = (
            t.needs_review if hasattr(t, "needs_review") else t.get("needs_review", False)
        )
        if needs_review or method in ("none", None) or cat_name in ("Uncategorized", "Needs Review"):
            unclassified_count += 1

        # Debit tracking
        if debit is not None and debit > Decimal("0"):
            debit_count += 1
            debit_total += debit
            all_amounts.append(debit)

            if debit > max_debit_amt:
                max_debit_amt = debit
                highest_debit = {
                    "transaction_id": t_id,
                    "amount": f"{debit:.2f}",
                    "description": t_desc,
                    "date": date_str,
                }

            if is_transfer:
                transfers_out += debit
            else:
                total_expenses += debit
                if cat_id:
                    category_sums[cat_id]["total"] += debit
                    category_sums[cat_id]["count"] += 1
                    category_sums[cat_id]["name"] = cat_name
                    category_sums[cat_id]["color"] = cat_color

        # Credit tracking
        if credit is not None and credit > Decimal("0"):
            credit_count += 1
            credit_total += credit
            all_amounts.append(credit)

            if credit > max_credit_amt:
                max_credit_amt = credit
                highest_credit = {
                    "transaction_id": t_id,
                    "amount": f"{credit:.2f}",
                    "description": t_desc,
                    "date": date_str,
                }

            if is_transfer:
                transfers_in += credit
            else:
                total_income += credit

        # Monthly tracking
        if date_str:
            month_key = date_str[:7]  # 'YYYY-MM'
            daily_counts[date_str] += 1
            if not is_transfer:
                if credit:
                    monthly_data[month_key]["income"] += credit
                if debit:
                    monthly_data[month_key]["expenses"] += debit

    net_cash_flow = total_income - total_expenses

    avg_transaction_amount = None
    if all_amounts:
        avg_transaction_amount = f"{(sum(all_amounts) / len(all_amounts)):.2f}"

    # Format category expenditure list
    category_expenditure = []
    for cid, data in sorted(category_sums.items(), key=lambda x: x[1]["total"], reverse=True):
        category_expenditure.append({
            "category_id": cid,
            "category_name": data["name"],
            "color": data["color"],
            "total": f"{data['total']:.2f}",
            "count": data["count"],
        })

    # Format monthly list sorted by month
    monthly = []
    for m in sorted(monthly_data.keys()):
        monthly.append({
            "month": m,
            "income": f"{monthly_data[m]['income']:.2f}",
            "expenses": f"{monthly_data[m]['expenses']:.2f}",
        })

    # Format daily transaction counts sorted by date
    daily_transaction_counts = []
    for d in sorted(daily_counts.keys()):
        daily_transaction_counts.append({
            "date": d,
            "count": daily_counts[d],
        })

    return {
        "scope": scope,
        "statement_id": statement_id,
        "total_income": f"{total_income:.2f}",
        "total_expenses": f"{total_expenses:.2f}",
        "net_cash_flow": f"{net_cash_flow:.2f}",
        "transfers_in": f"{transfers_in:.2f}",
        "transfers_out": f"{transfers_out:.2f}",
        "average_transaction_amount": avg_transaction_amount,
        "highest_debit": highest_debit,
        "highest_credit": highest_credit,
        "category_expenditure": category_expenditure,
        "monthly": monthly,
        "debit_credit_distribution": {
            "debit_count": debit_count,
            "credit_count": credit_count,
            "debit_total": f"{debit_total:.2f}",
            "credit_total": f"{credit_total:.2f}",
        },
        "daily_transaction_counts": daily_transaction_counts,
        "unclassified_count": unclassified_count,
    }
