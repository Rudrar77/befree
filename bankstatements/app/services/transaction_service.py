"""Transaction query and update services."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, List, Optional, Tuple
import sqlalchemy as sa
from sqlalchemy import func, or_
from app.errors import NotFoundError, ValidationError
from app.extensions import db
from app.models.category import Category
from app.models.transaction import Transaction


def list_transactions(
    statement_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category_id: Optional[str] = None,
    classification_method: Optional[str] = None,
    validation_status: Optional[str] = None,
    duplicate_status: Optional[str] = None,
    needs_review: Optional[bool] = None,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
    search: Optional[str] = None,
    sort_by: str = "transaction_date",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[Transaction], int]:
    """Query transactions with complete Appendix A5 filtering, sorting, and pagination."""
    query = db.session.query(Transaction).outerjoin(Category, Transaction.category_id == Category.id)

    if statement_id:
        query = query.filter(Transaction.statement_id == statement_id)
    if date_from:
        query = query.filter(Transaction.transaction_date >= date_from)
    if date_to:
        query = query.filter(Transaction.transaction_date <= date_to)
    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if classification_method:
        query = query.filter(Transaction.classification_method == classification_method)
    if validation_status:
        query = query.filter(Transaction.validation_status == validation_status)
    if duplicate_status:
        query = query.filter(Transaction.duplicate_status == duplicate_status)
    if needs_review is not None:
        query = query.filter(Transaction.needs_review == needs_review)

    if min_amount is not None:
        min_paise = int(min_amount * Decimal("100"))
        query = query.filter(
            or_(
                Transaction.debit >= min_paise,
                Transaction.credit >= min_paise,
            )
        )
    if max_amount is not None:
        max_paise = int(max_amount * Decimal("100"))
        query = query.filter(
            or_(
                Transaction.debit <= max_paise,
                Transaction.credit <= max_paise,
            )
        )

    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Transaction.description.ilike(search_pattern),
                Transaction.original_description.ilike(search_pattern),
                Transaction.reference_number.ilike(search_pattern),
            )
        )

    # Sorting
    sort_column: Any = Transaction.transaction_date
    if sort_by == "amount":
        sort_column = func.coalesce(Transaction.debit, Transaction.credit)
    elif sort_by == "category_name":
        sort_column = Category.name
    elif sort_by == "confidence":
        sort_column = Transaction.confidence

    if sort_dir.lower() == "asc":
        query = query.order_by(sort_column.asc().nulls_last())
    else:
        query = query.order_by(sort_column.desc().nulls_last())

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items, total


def get_transaction_by_id(transaction_id: str) -> Transaction:
    """Retrieve single transaction by ID or raise NotFoundError."""
    txn = db.session.get(Transaction, transaction_id)
    if not txn:
        raise NotFoundError(message=f"Transaction with ID '{transaction_id}' not found.")
    return txn


def update_transaction(
    transaction_id: str,
    category_id: Optional[str] = None,
    notes: Optional[str] = None,
    needs_review: Optional[bool] = None,
) -> Transaction:
    """Update transaction fields.

    Per Appendix A5:
    Setting category_id sets:
        - manual_override = True
        - classification_method = 'manual'
        - confidence = None
        - needs_review = False
    """
    txn = get_transaction_by_id(transaction_id)

    if category_id is not None:
        # Validate category exists
        cat = db.session.get(Category, category_id)
        if not cat:
            raise ValidationError(
                message=f"Category with ID '{category_id}' does not exist.",
                details=[{"field": "category_id", "issue": "Category not found."}],
            )
        txn.category_id = category_id
        txn.manual_override = True
        txn.classification_method = "manual"
        txn.confidence = None
        txn.needs_review = False

    if notes is not None:
        txn.notes = notes

    if needs_review is not None:
        txn.needs_review = needs_review

    db.session.commit()
    return txn
