"""Statement API endpoints matching Appendix A5."""

from __future__ import annotations

import logging
from typing import Any, List
from flask import current_app, jsonify, request
from app.api import api_bp
from app.errors import AppError, ValidationError
from app.extraction.transaction_normalizer import parse_date, parse_money
from app.services.processing_service import trigger_statement_processing
from app.services.statement_service import (
    delete_statement,
    get_statement_by_id,
    get_unresolved_rows,
    list_statements,
)
from app.services.transaction_service import list_transactions
from app.services.upload_service import validate_and_save_upload

logger = logging.getLogger(__name__)


@api_bp.route("/statements/upload", methods=["POST"])
def upload_statements() -> tuple[Any, int]:
    """Upload one or more statement PDF files.

    Per-file results; one bad file must not fail the others.
    Returns 201 {"results": [{"filename": "x.pdf", "statement": Statement | null, "error": ErrorObject | null}]}
    """
    if "files" not in request.files:
        raise ValidationError(
            message="No files provided in multipart request under field 'files'.",
            details=[{"field": "files", "issue": "Missing 'files' field in form-data."}],
        )

    uploaded_files = request.files.getlist("files")
    if not uploaded_files:
        raise ValidationError(
            message="Empty files field.",
            details=[{"field": "files", "issue": "No files uploaded."}],
        )

    upload_dir = current_app.config["UPLOAD_DIR"]
    max_mb = current_app.config.get("MAX_UPLOAD_MB", 16)

    results: List[dict[str, Any]] = []

    for f in uploaded_files:
        fname = f.filename or "unknown.pdf"
        try:
            stmt, _ = validate_and_save_upload(
                f,
                upload_dir=upload_dir,
                max_mb=max_mb,
                max_pages=current_app.config.get("MAX_DOCUMENT_PAGES", 500),
                password=request.form.get("password"),
            )
            results.append({
                "filename": fname,
                "statement": stmt.to_dict(),
                "error": None,
            })
        except AppError as err:
            results.append({
                "filename": fname,
                "statement": None,
                "error": err.to_dict()["error"],
            })
        except Exception:
            logger.exception("Unexpected error while processing uploaded file '%s'.", fname)
            results.append({
                "filename": fname,
                "statement": None,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Unexpected error processing upload.",
                },
            })

    return jsonify({"results": results}), 201


@api_bp.route("/statements", methods=["GET"])
def get_statements() -> tuple[Any, int]:
    """List statements with pagination and optional processing_status filter."""
    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 50, type=int), 200)
    processing_status = request.args.get("processing_status")

    items, total = list_statements(
        page=page, page_size=page_size, processing_status=processing_status
    )

    return jsonify({
        "items": [s.to_dict() for s in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }), 200


@api_bp.route("/statements/<uuid:statement_id>", methods=["GET"])
def get_statement(statement_id: Any) -> tuple[Any, int]:
    """Retrieve details for a single statement."""
    stmt = get_statement_by_id(str(statement_id))
    return jsonify(stmt.to_dict()), 200


@api_bp.route("/statements/<uuid:statement_id>/process", methods=["POST"])
def process_statement(statement_id: Any) -> tuple[Any, int]:
    """Enqueue statement for asynchronous background processing."""
    stmt = trigger_statement_processing(str(statement_id))
    return jsonify(stmt.to_status_dict()), 202


@api_bp.route("/statements/<uuid:statement_id>/status", methods=["GET"])
def get_statement_status(statement_id: Any) -> tuple[Any, int]:
    """Get current processing status of a statement."""
    stmt = get_statement_by_id(str(statement_id))
    return jsonify(stmt.to_status_dict()), 200


@api_bp.route("/statements/<uuid:statement_id>", methods=["DELETE"])
def remove_statement(statement_id: Any) -> tuple[Any, int]:
    """Delete a statement, its DB records, and the stored file."""
    delete_statement(str(statement_id))
    return "", 204


@api_bp.route("/statements/<uuid:statement_id>/transactions", methods=["GET"])
def get_statement_transactions(statement_id: Any) -> tuple[Any, int]:
    """Retrieve paginated transactions for a specific statement."""
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
        page=page,
        page_size=page_size,
    )

    return jsonify({
        "items": [t.to_dict() for t in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }), 200


@api_bp.route("/statements/<uuid:statement_id>/unresolved", methods=["GET"])
def get_statement_unresolved(statement_id: Any) -> tuple[Any, int]:
    """Retrieve unresolved rows for a statement."""
    rows = get_unresolved_rows(str(statement_id))
    return jsonify({
        "items": [r.to_dict() for r in rows],
    }), 200
