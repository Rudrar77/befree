"""Rule engine for deterministic transaction categorization."""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple


class RuleMatchResult:
    def __init__(
        self,
        category_id: str,
        category_name: str,
        rule_id: str,
        confidence: float,
    ) -> None:
        self.category_id = category_id
        self.category_name = category_name
        self.rule_id = rule_id
        self.confidence = confidence


def match_single_rule(description: str, rule: Any) -> bool:
    """Check if a description matches a rule (case-insensitive).

    Match types:
        - exact: exact word boundary match
        - partial: substring / contains match
        - regex: regular expression match
    """
    desc_lower = description.lower()
    kw_lower = rule.keyword.strip().lower()

    if rule.match_type == "exact":
        # Word boundary match
        pattern = r"\b" + re.escape(kw_lower) + r"\b"
        return re.search(pattern, desc_lower) is not None

    elif rule.match_type == "regex":
        try:
            return re.search(rule.keyword, description, re.IGNORECASE) is not None
        except re.error:
            return False

    else:  # 'partial' or fallback
        return kw_lower in desc_lower


def match_rules(
    description: str,
    rules: List[Any],
    direction: Optional[str] = None,
) -> Optional[RuleMatchResult]:
    """Evaluate description against all active rules and return the winning match.

    Conflict resolution:
        1. Higher priority number wins
        2. Longer keyword wins
        3. User-defined rule wins over system rule

    Direction:
        Rules with direction 'debit' or 'credit' only match that cash-flow side.
        'any' matches both. If the transaction direction is unknown, directional
        rules still match so metadata-only rows are not dropped.
    """
    matching_rules: List[Tuple[int, int, int, Any]] = []
    txn_dir = (direction or "any").lower()

    for rule in rules:
        if not rule.is_active:
            continue

        rule_dir = (getattr(rule, "direction", None) or "any").lower()
        if rule_dir in ("debit", "credit") and txn_dir in ("debit", "credit") and rule_dir != txn_dir:
            continue

        if match_single_rule(description, rule):
            # Sorting key tuple:
            # 1. priority (int, higher wins)
            # 2. keyword length (int, longer wins)
            # 3. is_user_defined (1 if true, 0 if false, user wins)
            priority = getattr(rule, "priority", 100)
            kw_len = len(rule.keyword)
            user_flag = 1 if getattr(rule, "is_user_defined", False) else 0
            matching_rules.append((priority, kw_len, user_flag, rule))

    if not matching_rules:
        return None

    # Sort descending by priority, then kw_len, then user_flag
    matching_rules.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    winner = matching_rules[0][3]

    # Rule confidence: between 0.85 and 0.95 (never 1.0 by default per spec)
    # Higher priority or exact matches get slightly higher confidence
    base_conf = 0.90
    if winner.match_type == "exact":
        base_conf = 0.95
    elif winner.priority >= 800:
        base_conf = 0.92

    cat_name = winner.category.name if getattr(winner, "category", None) else getattr(winner, "category_name", "")

    return RuleMatchResult(
        category_id=winner.category_id,
        category_name=cat_name,
        rule_id=winner.id,
        confidence=base_conf,
    )

