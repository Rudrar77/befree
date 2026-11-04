"""Feature extraction for transaction ML classification."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, List
import numpy as np
import pandas as pd


def extract_features_df(transactions: List[dict[str, Any]]) -> pd.DataFrame:
    """Transform transaction dicts into a DataFrame suitable for scikit-learn ColumnTransformer.

    Features created:
        - 'text': cleaned description string
        - 'is_debit': 1 if debit, 0 if credit
        - 'log_amount': log1p(amount)
    """
    rows = []
    for t in transactions:
        desc = str(t.get("description") or t.get("original_description") or "")
        debit = t.get("debit")
        credit = t.get("credit")

        def _is_valid_num(v: Any) -> bool:
            if v is None:
                return False
            if isinstance(v, float) and math.isnan(v):
                return False
            if isinstance(v, str) and (not v.strip() or v.strip().lower() in ("nan", "none", "null", "—")):
                return False
            return True

        has_debit = _is_valid_num(debit) and Decimal(str(debit)) > Decimal("0")
        has_credit = _is_valid_num(credit) and Decimal(str(credit)) > Decimal("0")

        if has_debit:
            is_debit = 1.0
            amt = float(debit)
        elif has_credit:
            is_debit = 0.0
            amt = float(credit)
        else:
            is_debit = 1.0
            amt = 0.0

        log_amt = float(np.log1p(max(amt, 0.0)))

        rows.append({
            "text": desc,
            "is_debit": is_debit,
            "log_amount": log_amt,
        })

    return pd.DataFrame(rows)
