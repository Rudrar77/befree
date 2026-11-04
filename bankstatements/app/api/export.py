"""Export API endpoint matching Appendix A5."""

from __future__ import annotations

from typing import Any
from flask import Response, request, send_file
from app.analytics.financial_analytics import compute_financial_analytics
from app.api import api_bp
from app.errors import ValidationError
from app.export.csv_exporter import export_transactions_to_csv
from app.export.excel_exporter import export_statement_to_excel
from app.extensions import db
from app.extraction.transaction_normalizer import parse_date, parse_money
from app.models.category import Category
from app.models.validation_result import ValidationResult
from app.services.statement_service import get_statement_by_id
from app.services.transaction_service import list_transactions


@api_bp.route("/export/<uuid:statement_id>", methods=["GET"])
def export_statement(statement_id: Any) -> Any:
    """Download transactions in xlsx or csv format with filtering."""
    fmt = request.args.get("format", "").lower()
    if fmt not in ("xlsx", "csv"):
        raise ValidationError(
            message="Query parameter 'format' is required and must be 'xlsx' or 'csv'.",
            details=[{"field": "format", "issue": "Must be 'xlsx' or 'csv'."}],
        )

    stmt = get_statement_by_id(str(statement_id))

    # Apply filters
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

    # Get all filtered transactions (up to 10,000 for export)
    txns, _ = list_transactions(
        statement_id=str(statement_id),
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
        page=1,
        page_size=10000,
    )

    clean_base = stmt.original_filename.rsplit(".", 1)[0]
    filename = f"{clean_base}_export.{fmt}"

    if fmt == "csv":
        bytes_io = export_transactions_to_csv(txns)
        return send_file(
            bytes_io,
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename,
        )

    # For XLSX: include validation issues and analytics
    issues = db.session.query(ValidationResult).filter_by(statement_id=str(statement_id)).all()
    transfer_cats = db.session.query(Category.id).filter_by(is_transfer=True).all()
    transfer_cat_ids = {c[0] for c in transfer_cats}

    analytics = compute_financial_analytics(
        transactions=txns,
        scope="statement",
        statement_id=str(statement_id),
        transfer_category_ids=transfer_cat_ids,
    )

    excel_io = export_statement_to_excel(
        statement=stmt,
        transactions=txns,
        validation_issues=issues,
        analytics=analytics,
    )

    return send_file(
        excel_io,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )

