"""Analytics API endpoints matching Appendix A4 and A5."""

from __future__ import annotations

from typing import Any
from flask import jsonify, request
from sqlalchemy import desc
from sqlalchemy.orm import joinedload
from app.analytics.financial_analytics import compute_financial_analytics
from app.api import api_bp
from app.extensions import db
from app.extraction.transaction_normalizer import parse_date
from app.models.category import Category
from app.models.statement import Statement
from app.models.transaction import Transaction
from app.services.statement_service import get_statement_by_id


@api_bp.route("/analytics", methods=["GET"])
def get_global_analytics() -> tuple[Any, int]:
    """Calculate aggregated analytics across all statements."""
    date_from = parse_date(request.args.get("date_from")) if request.args.get("date_from") else None
    date_to = parse_date(request.args.get("date_to")) if request.args.get("date_to") else None

    query = (
        db.session.query(Transaction)
        .join(Statement, Transaction.statement_id == Statement.id)
        .options(joinedload(Transaction.category))
        .filter(
            Statement.processing_status.in_(
                ("completed", "completed_with_warnings")
            )
        )
    )
    if date_from:
        query = query.filter(Transaction.transaction_date >= date_from)
    if date_to:
        query = query.filter(Transaction.transaction_date <= date_to)

    txns = query.all()

    # Get transfer category IDs
    transfer_cats = db.session.query(Category.id).filter_by(is_transfer=True).all()
    transfer_cat_ids = {c[0] for c in transfer_cats}

    analytics = compute_financial_analytics(
        transactions=txns,
        scope="all",
        statement_id=None,
        transfer_category_ids=transfer_cat_ids,
    )
    return jsonify(analytics), 200


@api_bp.route("/dashboard/recent-transactions", methods=["GET"])
def get_dashboard_recent_transactions() -> tuple[Any, int]:
    """Return recent extracted transactions from successfully processed statements."""
    completed_statuses = ("completed", "completed_with_warnings")
    query = (
        db.session.query(Transaction, Statement)
        .join(Statement, Transaction.statement_id == Statement.id)
        .filter(Statement.processing_status.in_(completed_statuses))
    )
    total = query.count()
    rows = (
        query.order_by(
            Transaction.transaction_date.desc().nullslast(),
            desc(Transaction.created_at),
        )
        .limit(10)
        .all()
    )

    return jsonify({
        "items": [
            {
                **transaction.to_dict(),
                "statement_filename": statement.original_filename,
                "statement_bank_name": statement.bank_name,
                "category_color": transaction.category.color if transaction.category else None,
            }
            for transaction, statement in rows
        ],
        "total": total,
    }), 200


@api_bp.route("/analytics/<uuid:statement_id>", methods=["GET"])
def get_statement_analytics(statement_id: Any) -> tuple[Any, int]:
    """Calculate analytics for a specific statement."""
    # Ensure statement exists
    get_statement_by_id(str(statement_id))

    date_from = parse_date(request.args.get("date_from")) if request.args.get("date_from") else None
    date_to = parse_date(request.args.get("date_to")) if request.args.get("date_to") else None

    query = db.session.query(Transaction).options(joinedload(Transaction.category)).filter_by(statement_id=str(statement_id))
    if date_from:
        query = query.filter(Transaction.transaction_date >= date_from)
    if date_to:
        query = query.filter(Transaction.transaction_date <= date_to)

    txns = query.all()

    transfer_cats = db.session.query(Category.id).filter_by(is_transfer=True).all()
    transfer_cat_ids = {c[0] for c in transfer_cats}

    analytics = compute_financial_analytics(
        transactions=txns,
        scope="statement",
        statement_id=str(statement_id),
        transfer_category_ids=transfer_cat_ids,
    )
    return jsonify(analytics), 200
