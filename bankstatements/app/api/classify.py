"""Stateless prediction endpoints for the pretrained transaction classifier."""

from __future__ import annotations

from typing import Any

from flask import current_app, jsonify, request

from app.api import api_bp
from app.classification.confidence import classify_transactions_pipeline
from app.errors import ValidationError
from app.extensions import db
from app.models.category import Category
from app.models.classification_rule import ClassificationRule
from app.services.pretrained_classifier import (
    MODEL_CATEGORIES,
    get_pretrained_classifier,
)

MAX_BULK_TRANSACTIONS = 500
MAX_DESCRIPTION_LENGTH = 4000


def _validate_description(value: Any) -> str:
    if not isinstance(value, str):
        raise ValidationError(
            message="description must be a string.",
            details=[{"field": "description", "issue": "Expected a string."}],
        )
    if len(value) > MAX_DESCRIPTION_LENGTH:
        raise ValidationError(
            message=f"description must be at most {MAX_DESCRIPTION_LENGTH} characters.",
            details=[{"field": "description", "issue": "Description is too long."}],
        )
    return value


def _serialize_result(transaction: dict[str, Any]) -> dict[str, Any]:
    method = transaction.get("classification_method", "none")
    needs_review = bool(transaction.get("needs_review", True))
    return {
        "transaction_id": transaction.get("id") or transaction.get("transaction_id"),
        "date": transaction.get("date") or transaction.get("transaction_date"),
        "description": transaction.get("description", ""),
        "debit": transaction.get("debit"),
        "credit": transaction.get("credit"),
        "balance": transaction.get("balance"),
        "category": transaction.get("classified_category", "Unclassified"),
        "confidence": transaction.get("confidence") or 0.0,
        "classification_method": method,
        "needs_review": needs_review,
        "status": "needs_review" if needs_review else "classified",
        "reason": (
            "no_rule_or_model_category"
            if method == "none"
            else "below_confidence_threshold"
            if needs_review and method == "ml"
            else None
        ),
    }


def _classify_transactions(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rules = db.session.query(ClassificationRule).join(Category).all()
    categories = db.session.query(Category).all()
    category_map = {category.name: category for category in categories}

    classify_transactions_pipeline(
        transactions,
        rules=rules,
        category_map_by_name=category_map,
        ml_classifier=get_pretrained_classifier(),
        confidence_threshold=float(current_app.config.get("CONFIDENCE_THRESHOLD", 0.70)),
        ml_confidence_threshold=float(
            current_app.config.get("PRETRAINED_TRANSACTION_CONFIDENCE_THRESHOLD", 0.30)
        ),
    )

    categories_by_id = {category.id: category.name for category in categories}
    for transaction in transactions:
        transaction["classified_category"] = categories_by_id.get(
            transaction.get("category_id"), "Unclassified"
        )
    return transactions


@api_bp.route("/classify", methods=["POST"])
def classify_one() -> tuple[Any, int]:
    """Classify one transaction with rules first and ML only as a fallback."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or "description" not in body:
        raise ValidationError(
            message="A transaction description is required.",
            details=[{"field": "description", "issue": "Missing required field."}],
        )

    transaction = dict(body)
    transaction["description"] = _validate_description(body["description"])
    result = _classify_transactions([transaction])[0]
    return jsonify(_serialize_result(result)), 200


@api_bp.route("/classify/bulk", methods=["POST"])
def classify_bulk() -> tuple[Any, int]:
    """Classify up to 500 transactions using rules before the ML fallback."""
    body = request.get_json(silent=True)
    if isinstance(body, list):
        transactions = body
    elif isinstance(body, dict):
        transactions = body.get("transactions")
    else:
        transactions = None

    if not isinstance(transactions, list):
        raise ValidationError(
            message="transactions must be a JSON array.",
            details=[{"field": "transactions", "issue": "Expected an array."}],
        )
    if len(transactions) > MAX_BULK_TRANSACTIONS:
        raise ValidationError(
            message=f"At most {MAX_BULK_TRANSACTIONS} transactions may be classified at once.",
            details=[{"field": "transactions", "issue": "Batch is too large."}],
        )

    normalized_transactions: list[dict[str, Any]] = []
    for index, transaction in enumerate(transactions):
        if isinstance(transaction, str):
            normalized_transactions.append(
                {"description": _validate_description(transaction)}
            )
        elif isinstance(transaction, dict) and "description" in transaction:
            try:
                normalized = dict(transaction)
                normalized["description"] = _validate_description(
                    transaction["description"]
                )
                normalized_transactions.append(normalized)
            except ValidationError as exc:
                raise ValidationError(
                    message=f"Invalid transaction at index {index}: {exc.message}",
                    details=[{"field": f"transactions[{index}].description", "issue": "Expected a string of at most 4000 characters."}],
                ) from exc
        else:
            raise ValidationError(
                message=f"Invalid transaction at index {index}.",
                details=[{"field": f"transactions[{index}]", "issue": "Expected a description string or object."}],
            )

    classified = _classify_transactions(normalized_transactions)
    results = [_serialize_result(transaction) for transaction in classified]
    return jsonify({"items": results, "total": len(results)}), 200


@api_bp.route("/classify/categories", methods=["GET"])
def get_classifier_categories() -> tuple[Any, int]:
    """Return the exact category labels used by the upstream trained model."""
    return jsonify({"categories": list(MODEL_CATEGORIES), "total": len(MODEL_CATEGORIES)}), 200


@api_bp.route("/classify/status", methods=["GET"])
def get_classifier_status() -> tuple[Any, int]:
    """Report artifact availability and whether it has been loaded into memory."""
    return jsonify(get_pretrained_classifier().status()), 200
