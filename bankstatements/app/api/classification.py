"""Classification API endpoint matching Appendix A5."""

from __future__ import annotations

from typing import Any
from flask import current_app, jsonify, request
from app.api import api_bp
from app.classification.confidence import classify_transactions_pipeline
from app.errors import NotFoundError, ValidationError
from app.extensions import db
from app.models.category import Category
from app.models.classification_rule import ClassificationRule
from app.models.statement import Statement
from app.models.transaction import Transaction
from app.services.pretrained_classifier import get_pretrained_classifier


@api_bp.route("/classification/classify", methods=["POST"])
def classify_statement_transactions() -> tuple[Any, int]:
    """Classify (or re-classify) transactions for a statement.

    Rules:
        - Manual overrides are NEVER overwritten (unless force=true is explicitly set,
          though default force=false keeps all manual overrides).
        - Returns counts: {"statement_id", "classified", "needs_review", "by_method": {"rule": int, "ml": int, "none": int}}
    """
    body = request.get_json(silent=True) or {}
    statement_id = body.get("statement_id")
    force = bool(body.get("force", False))

    if not statement_id:
        raise ValidationError(
            message="statement_id is required in request body.",
            details=[{"field": "statement_id", "issue": "Missing statement_id."}],
        )

    stmt = db.session.get(Statement, str(statement_id))
    if not stmt:
        raise NotFoundError(message=f"Statement with ID '{statement_id}' not found.")

    txns = db.session.query(Transaction).filter_by(statement_id=str(statement_id)).all()
    if not txns:
        return jsonify({
            "statement_id": str(statement_id),
            "classified": 0,
            "needs_review": 0,
            "by_method": {"rule": 0, "ml": 0, "none": 0},
        }), 200

    rules = db.session.query(ClassificationRule).join(Category).all()
    all_cats = db.session.query(Category).all()
    cat_map = {c.name: c for c in all_cats}

    ml_model = get_pretrained_classifier()
    conf_threshold = current_app.config.get("CONFIDENCE_THRESHOLD", 0.70)
    ml_conf_threshold = current_app.config.get(
        "PRETRAINED_TRANSACTION_CONFIDENCE_THRESHOLD", 0.30
    )

    # Convert transactions to dicts for pipeline
    txn_dicts = [t.to_dict() for t in txns]
    for idx, t in enumerate(txns):
        txn_dicts[idx]["manual_override"] = t.manual_override

    summary = classify_transactions_pipeline(
        txn_dicts,
        rules=rules,
        category_map_by_name=cat_map,
        ml_classifier=ml_model,
        confidence_threshold=conf_threshold,
        ml_confidence_threshold=ml_conf_threshold,
        force=force,
    )

    # Apply back to ORM models
    for t_orm, t_res in zip(txns, txn_dicts):
        if t_orm.manual_override and not force:
            continue
        t_orm.category_id = t_res.get("category_id")
        t_orm.classification_method = t_res.get("classification_method", "none")
        t_orm.confidence = t_res.get("confidence")
        t_orm.applied_rule_id = t_res.get("applied_rule_id")
        t_orm.model_version = t_res.get("model_version")
        t_orm.needs_review = t_res.get("needs_review", False)

    db.session.commit()

    total_classified = summary.get("rule", 0) + summary.get("ml", 0)

    return jsonify({
        "statement_id": str(statement_id),
        "classified": total_classified,
        "needs_review": summary.get("needs_review", 0),
        "by_method": {
            "rule": summary.get("rule", 0),
            "ml": summary.get("ml", 0),
            "none": summary.get("none", 0),
        },
    }), 200
