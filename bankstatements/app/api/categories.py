"""Category and rule management API endpoints matching Appendix A5."""

from __future__ import annotations

from typing import Any
from flask import jsonify, request
from app.api import api_bp
from app.errors import ValidationError
from app.services.category_service import (
    create_category,
    create_rule,
    delete_rule,
    get_category_by_id,
    get_rule_by_id,
    list_categories,
    list_rules,
    update_category,
    update_rule,
)


# -----------------------------------------------------------------------------
# Rules endpoints (declared first to avoid any routing collision)
# -----------------------------------------------------------------------------

@api_bp.route("/categories/rules", methods=["GET"])
def get_category_rules() -> tuple[Any, int]:
    """Retrieve classification rules, optionally filtered by category_id."""
    category_id = request.args.get("category_id")
    rules = list_rules(category_id=category_id)
    return jsonify({
        "items": [r.to_dict() for r in rules],
    }), 200


@api_bp.route("/categories/rules", methods=["POST"])
def post_category_rule() -> tuple[Any, int]:
    """Create a new classification rule."""
    body = request.get_json(silent=True) or {}
    category_id = body.get("category_id")
    keyword = body.get("keyword")
    match_type = body.get("match_type", "partial")
    priority = body.get("priority", 100)
    direction = body.get("direction", "any")

    if not category_id or not keyword:
        raise ValidationError(
            message="category_id and keyword are required.",
            details=[{"field": "keyword", "issue": "Missing required field."}],
        )

    rule = create_rule(
        category_id=str(category_id),
        keyword=str(keyword),
        match_type=str(match_type),
        priority=int(priority),
        direction=str(direction),
    )
    return jsonify(rule.to_dict()), 201


@api_bp.route("/categories/rules/<uuid:rule_id>", methods=["PATCH"])
def patch_category_rule(rule_id: Any) -> tuple[Any, int]:
    """Update classification rule."""
    body = request.get_json(silent=True) or {}
    rule = update_rule(
        rule_id=str(rule_id),
        category_id=body.get("category_id"),
        keyword=body.get("keyword"),
        match_type=body.get("match_type"),
        priority=body.get("priority"),
        is_active=body.get("is_active"),
        direction=body.get("direction"),
    )
    return jsonify(rule.to_dict()), 200


@api_bp.route("/categories/rules/<uuid:rule_id>", methods=["DELETE"])
def remove_category_rule(rule_id: Any) -> tuple[Any, int]:
    """Delete a user-defined classification rule."""
    delete_rule(str(rule_id))
    return "", 204


# -----------------------------------------------------------------------------
# Category endpoints
# -----------------------------------------------------------------------------

@api_bp.route("/categories", methods=["GET"])
def get_categories() -> tuple[Any, int]:
    """Retrieve all categories."""
    cats = list_categories()
    return jsonify({
        "items": [c.to_dict() for c in cats],
    }), 200


@api_bp.route("/categories", methods=["POST"])
def post_category() -> tuple[Any, int]:
    """Create a new category. 409 on duplicate name."""
    body = request.get_json(silent=True) or {}
    name = body.get("name")
    if not name:
        raise ValidationError(
            message="name is required.",
            details=[{"field": "name", "issue": "Missing required field."}],
        )

    cat = create_category(
        name=str(name),
        is_transfer=bool(body.get("is_transfer", False)),
        color=body.get("color"),
    )
    return jsonify(cat.to_dict()), 201


@api_bp.route("/categories/<uuid:category_id>", methods=["PATCH"])
def patch_category(category_id: Any) -> tuple[Any, int]:
    """Update a category."""
    body = request.get_json(silent=True) or {}
    cat = update_category(
        category_id=str(category_id),
        name=body.get("name"),
        is_active=body.get("is_active"),
        is_transfer=body.get("is_transfer"),
        color=body.get("color"),
    )
    return jsonify(cat.to_dict()), 200

