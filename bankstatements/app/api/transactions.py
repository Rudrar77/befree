"""Transaction API endpoints matching Appendix A5."""

from __future__ import annotations

from typing import Any
from flask import jsonify, request
from app.api import api_bp
from app.errors import ValidationError
from app.extraction.transaction_normalizer import parse_date, parse_money
from app.services.transaction_service import (
    get_transaction_by_id,
    list_transactions,
    update_transaction,
)


@api_bp.route("/transactions", methods=["GET"])
def get_all_transactions() -> tuple[Any, int]:
    """Retrieve paginated transactions across all statements."""
    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 50, type=int), 200)

    date_from = parse_date(request.args.get("date_from")) if request.args.get("date_from") else None
    date_to = parse_date(request.args.get("date_to")) if request.args.get("date_to") else None
    cat_id = request.args.get("category_id")
    method = request.args.get("classification_method")
    val_status = request.args.get("validation_status")
    dup_status = request.args.get("duplicate_status")

    needs_rev_str = request.args.get("needs_review")
    needs_review = None
    if needs_rev_str is not None:
        needs_review = needs_rev_str.lower() in ("true", "1")

    min_amt = parse_money(request.args.get("min_amount"))
    max_amt = parse_money(request.args.get("max_amount"))
    search = request.args.get("search")
    sort_by = request.args.get("sort_by", "transaction_date")
    sort_dir = request.args.get("sort_dir", "desc")

    items, total = list_transactions(
        statement_id=None,
        date_from=date_from,
        date_to=date_to,
        category_id=cat_id,
        classification_method=method,
        validation_status=val_status,
        duplicate_status=dup_status,
        needs_review=needs_review,
        min_amount=min_amt,
        max_amount=max_amt,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )

    return jsonify({
        "items": [t.to_dict() for t in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }), 200


@api_bp.route("/transactions/<uuid:transaction_id>", methods=["GET"])
def get_transaction(transaction_id: Any) -> tuple[Any, int]:
    """Retrieve single transaction."""
    txn = get_transaction_by_id(str(transaction_id))
    return jsonify(txn.to_dict()), 200


@api_bp.route("/transactions/<uuid:transaction_id>", methods=["PATCH"])
def patch_transaction(transaction_id: Any) -> tuple[Any, int]:
    """Manually correct category, resolve review, or add notes to transaction."""
    body = request.get_json(silent=True) or {}
    category_id = body.get("category_id")
    notes = body.get("notes")
    needs_review = body.get("needs_review")

    if "needs_review" in body and not isinstance(needs_review, bool):
        raise ValidationError(
            message="needs_review must be a boolean.",
            details=[{"field": "needs_review", "issue": "Expected a boolean."}],
        )

    txn = update_transaction(
        transaction_id=str(transaction_id),
        category_id=category_id,
        notes=notes,
        needs_review=needs_review,
    )
    return jsonify(txn.to_dict()), 200
