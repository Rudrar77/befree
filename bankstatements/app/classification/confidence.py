"""Classification orchestration pipeline."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Protocol

from app.classification.rule_engine import match_rules
from app.services.pretrained_classifier import ClassifierUnavailableError

logger = logging.getLogger(__name__)
UNCLASSIFIED_CATEGORY_NAMES = {"uncategorized", "unclassified", "needs review"}


class TransactionPredictor(Protocol):
    model_version: str

    def predict(
        self, transactions: List[dict[str, Any]]
    ) -> List[tuple[str | None, float]]: ...


def _valid_category(
    category_map_by_name: Dict[str, Any],
    category_name: str | None,
    category_id: str | None,
) -> Any | None:
    if not category_name or category_name.strip().lower() in UNCLASSIFIED_CATEGORY_NAMES:
        return None
    category = category_map_by_name.get(category_name)
    if (
        category is None
        or getattr(category, "id", None) != category_id
        or not getattr(category, "is_active", True)
    ):
        return None
    return category


def _positive_score(score: Any) -> float:
    try:
        normalized_score = float(score)
    except (TypeError, ValueError):
        return 0.0
    return normalized_score if normalized_score > 0 else 0.0


def _transaction_direction(txn: dict[str, Any]) -> str:
    debit = txn.get("debit")
    credit = txn.get("credit")
    has_debit = debit not in (None, "", "0", "0.00", "0.0")
    has_credit = credit not in (None, "", "0", "0.00", "0.0")
    if has_debit and not has_credit:
        return "debit"
    if has_credit and not has_debit:
        return "credit"
    return "any"


def classify_transactions_pipeline(
    transactions: List[dict[str, Any]],
    rules: List[Any],
    category_map_by_name: Dict[str, Any],
    ml_classifier: Optional[TransactionPredictor] = None,
    confidence_threshold: float = 0.70,
    ml_confidence_threshold: Optional[float] = None,
    force: bool = False,
) -> dict[str, int]:
    """Execute classification pipeline across transactions in-place.

    Pipeline:
        1. Skip if manual_override is True
        2. Apply deterministic rules, preserving every usable rule match
        3. Run ML only for transactions left unresolved by the rules
        4. Mark uncertain ML results and unresolved transactions for review

    Returns summary counts:
        {"total": int, "rule": int, "ml": int, "none": int, "needs_review": int}
    """
    counts = {"total": 0, "rule": 0, "ml": 0, "none": 0, "needs_review": 0}
    ml_review_threshold = (
        confidence_threshold
        if ml_confidence_threshold is None
        else ml_confidence_threshold
    )

    # Filter transactions needing ML
    ml_candidates: List[dict[str, Any]] = []

    for txn in transactions:
        # Never overwrite manual override
        if txn.get("manual_override") and not force:
            continue

        counts["total"] += 1
        desc = txn.get("description", "")
        if not isinstance(desc, str) or not desc.strip() or desc.strip().lower() in {
            "unspecified transaction",
            "unknown transaction",
        }:
            txn["category_id"] = None
            txn["classification_method"] = "none"
            txn["confidence"] = 0.0
            txn["applied_rule_id"] = None
            txn["model_version"] = None
            txn["needs_review"] = True
            counts["none"] += 1
            counts["needs_review"] += 1
            continue

        # 1. Try rule match
        rule_result = match_rules(desc, rules, direction=_transaction_direction(txn))

        rule_category = (
            _valid_category(
                category_map_by_name,
                getattr(rule_result, "category_name", None),
                getattr(rule_result, "category_id", None),
            )
            if rule_result
            else None
        )
        rule_score = _positive_score(getattr(rule_result, "confidence", 0)) if rule_result else 0.0

        if rule_result and rule_category and rule_score > 0:
            txn["category_id"] = rule_result.category_id
            txn["classification_method"] = "rule"
            txn["confidence"] = rule_score
            txn["applied_rule_id"] = rule_result.rule_id
            txn["model_version"] = None

            txn["needs_review"] = rule_score < confidence_threshold
            if txn["needs_review"]:
                counts["needs_review"] += 1

            counts["rule"] += 1
        else:
            # Queue for ML
            ml_candidates.append(txn)

    # 2. Run ML only after all transactions have been checked against the rules.
    predictions: Optional[List[tuple[str | None, float]]] = None
    if ml_candidates and ml_classifier:
        try:
            predictions = ml_classifier.predict(ml_candidates)
        except ClassifierUnavailableError:
            logger.exception(
                "Pretrained classifier unavailable; unresolved transactions need manual review."
            )
            ml_classifier = None

    if ml_candidates and ml_classifier and predictions is not None:
        for txn, (pred_cat_name, conf) in zip(ml_candidates, predictions):
            cat_obj = _valid_category(
                category_map_by_name,
                pred_cat_name,
                getattr(category_map_by_name.get(pred_cat_name), "id", None)
                if pred_cat_name
                else None,
            )
            ml_score = _positive_score(conf)
            if cat_obj and ml_score > 0:
                txn["category_id"] = cat_obj.id
                txn["classification_method"] = "ml"
                txn["confidence"] = ml_score
                txn["applied_rule_id"] = None
                txn["model_version"] = ml_classifier.model_version
                txn["needs_review"] = ml_score < ml_review_threshold
                counts["ml"] += 1
                if txn["needs_review"]:
                    counts["needs_review"] += 1
            else:
                # Below threshold or unknown category
                txn["category_id"] = None
                txn["classification_method"] = "none"
                txn["confidence"] = 0.0
                txn["applied_rule_id"] = None
                txn["model_version"] = None
                txn["needs_review"] = True
                counts["needs_review"] += 1
                counts["none"] += 1
    else:
        # No ML model: fallback for remaining
        for txn in ml_candidates:
            txn["category_id"] = None
            txn["classification_method"] = "none"
            txn["confidence"] = 0.0
            txn["applied_rule_id"] = None
            txn["model_version"] = None
            txn["needs_review"] = True
            counts["none"] += 1
            counts["needs_review"] += 1

    return counts
