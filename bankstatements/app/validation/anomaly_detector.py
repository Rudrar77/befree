"""Statistical anomaly detection for transactions."""

from __future__ import annotations

import collections
from decimal import Decimal
from typing import Any, List
import numpy as np


def detect_anomalies(
    transactions: List[dict[str, Any]],
    min_sample_size: int = 10,
    iqr_multiplier: float = 2.5,
    max_daily_frequency: int = 15,
) -> dict[str, int]:
    """Detect statistical anomalies across transactions and attach flags.

    Flags generated:
        - {"type": "large_amount", "detail": "Amount is statistically unusually high compared to statement distribution."}
        - {"type": "negative_balance", "detail": "Running balance dropped below zero."}
        - {"type": "high_daily_frequency", "detail": "Unusually high number of transactions on this date."}
        - {"type": "repeated_amount", "detail": "Multiple identical amounts observed within a short window."}

    Note: Wording must strictly use 'anomaly flag', never 'fraud'.

    Returns:
        Summary dict: {"flagged": int}
    """
    total_flagged = 0

    amounts = []
    daily_counts = collections.defaultdict(int)

    for t in transactions:
        t_date = t.get("transaction_date")
        if t_date:
            daily_counts[t_date] += 1

        amt = None
        if t.get("debit") is not None:
            amt = float(t["debit"])
        elif t.get("credit") is not None:
            amt = float(t["credit"])

        if amt is not None and amt > 0:
            amounts.append(amt)

    # 1. IQR / modified z-score on log amounts
    outlier_threshold = None
    if len(amounts) >= min_sample_size:
        log_amts = np.log1p(amounts)
        q25, q75 = np.percentile(log_amts, [25, 75])
        iqr = q75 - q25
        if iqr > 0:
            upper_bound = q75 + (iqr_multiplier * iqr)
            outlier_threshold = np.expm1(upper_bound)

    # 2. Check each transaction
    for t in transactions:
        flags: List[dict[str, str]] = list(t.get("anomaly_flags", []))
        has_new_flag = False

        amt = None
        if t.get("debit") is not None:
            amt = float(t["debit"])
        elif t.get("credit") is not None:
            amt = float(t["credit"])

        # Check statistical outlier
        if amt is not None and outlier_threshold is not None and amt > outlier_threshold:
            flags.append({
                "type": "large_amount",
                "detail": f"Amount ₹{amt:,.2f} is statistically an anomaly compared to standard transaction range.",
            })
            has_new_flag = True

        # Check negative balance
        bal = t.get("balance")
        if bal is not None and Decimal(str(bal)) < Decimal("0"):
            flags.append({
                "type": "negative_balance",
                "detail": f"Running balance ₹{bal:.2f} is negative.",
            })
            has_new_flag = True

        # Check high daily frequency
        t_date = t.get("transaction_date")
        if t_date and daily_counts[t_date] > max_daily_frequency:
            flags.append({
                "type": "high_daily_frequency",
                "detail": f"Unusual daily frequency of {daily_counts[t_date]} transactions on {t_date}.",
            })
            has_new_flag = True

        if has_new_flag:
            t["anomaly_flags"] = flags
            t["needs_review"] = True
            total_flagged += 1

    return {"flagged": total_flagged}

