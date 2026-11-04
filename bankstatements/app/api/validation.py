"""Validation API endpoints matching Appendix A4 and A5."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from flask import current_app, jsonify
from app.api import api_bp
from app.extensions import db
from app.models.statement import Statement
from app.models.transaction import Transaction
from app.models.unresolved_row import UnresolvedRow
from app.models.validation_result import ValidationResult
from app.services.statement_service import get_statement_by_id
from app.validation.anomaly_detector import detect_anomalies
from app.validation.balance_reconciliation import reconcile_statement_balances
from app.validation.data_validator import validate_statement_data
from app.validation.duplicate_detector import detect_duplicates


def build_validation_report(statement_id: str) -> dict[str, Any]:
    """Assemble complete ValidationReport for a statement."""
    stmt = get_statement_by_id(statement_id)
    txns = db.session.query(Transaction).filter_by(statement_id=statement_id).all()
    issues = db.session.query(ValidationResult).filter_by(statement_id=statement_id).all()

    # Recompute / format reconciliation
    recon_tol = Decimal(str(current_app.config.get("RECONCILIATION_TOLERANCE", 0.01)))
    recon_res = reconcile_statement_balances(
        opening_balance=stmt.opening_balance,
        closing_balance=stmt.closing_balance,
        transactions=[t.to_dict() for t in txns],
        tolerance=recon_tol,
    )

    exact_dup = sum(1 for t in txns if t.duplicate_status == "exact_duplicate")
    possible_dup = sum(1 for t in txns if t.duplicate_status == "possible_duplicate")
    anomaly_cnt = sum(1 for t in txns if len(t.anomaly_flags) > 0)

    has_error = any(i.severity == "error" for i in issues) or recon_res["status"] == "mismatch"
    has_warning = any(i.severity == "warning" for i in issues) or possible_dup > 0 or anomaly_cnt > 0

    if has_error:
        overall_status = "error"
    elif has_warning:
        overall_status = "warning"
    else:
        overall_status = "valid"

    return {
        "statement_id": stmt.id,
        "overall_status": overall_status,
        "issues": [i.to_dict() for i in issues],
        "reconciliation": recon_res,
        "duplicate_summary": {"exact": exact_dup, "possible": possible_dup},
        "anomaly_summary": {"flagged": anomaly_cnt},
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@api_bp.route("/validation/<uuid:statement_id>", methods=["GET"])
def get_validation_report(statement_id: Any) -> tuple[Any, int]:
    """Retrieve validation report for a statement."""
    report = build_validation_report(str(statement_id))
    return jsonify(report), 200


@api_bp.route("/validation/<uuid:statement_id>/recheck", methods=["POST"])
def recheck_validation(statement_id: Any) -> tuple[Any, int]:
    """Re-run validation checks, duplicate detection, reconciliation, and anomalies."""
    stmt = get_statement_by_id(str(statement_id))
    txns = db.session.query(Transaction).filter_by(statement_id=str(statement_id)).all()
    unresolved = db.session.query(UnresolvedRow).filter_by(statement_id=str(statement_id)).all()

    txn_dicts = [t.to_dict() for t in txns]
    unresolved_dicts = [u.to_dict() for u in unresolved]

    # Re-run duplicates and anomalies
    detect_duplicates(txn_dicts)
    detect_anomalies(txn_dicts)

    # Re-run data validation
    new_issues = validate_statement_data(
        statement_info=stmt.to_dict(),
        transactions=txn_dicts,
        unresolved_rows=unresolved_dicts,
    )

    # Update transactions in DB
    for t_orm, t_dict in zip(txns, txn_dicts):
        t_orm.duplicate_status = t_dict.get("duplicate_status", "none")
        t_orm.duplicate_of = t_dict.get("duplicate_of")
        t_orm.validation_status = t_dict.get("validation_status", "valid")
        t_orm.anomaly_flags = t_dict.get("anomaly_flags", [])

    # Replace validation results in DB
    db.session.query(ValidationResult).filter_by(statement_id=str(statement_id)).delete()
    for v_dict in new_issues:
        v_obj = ValidationResult(
            id=v_dict["id"],
            statement_id=str(statement_id),
            severity=v_dict["severity"],
            code=v_dict["code"],
            message=v_dict["message"],
            transaction_id=v_dict.get("transaction_id"),
            transaction_description=v_dict.get("transaction_description"),
        )
        db.session.add(v_obj)

    db.session.commit()

    report = build_validation_report(str(statement_id))
    return jsonify(report), 200

