"""Category and classification rule services."""

from __future__ import annotations

from typing import Any, List, Optional
from app.errors import ConflictError, NotFoundError, ValidationError
from app.extensions import db
from app.models.category import Category
from app.models.classification_rule import ClassificationRule, MatchType


def list_categories() -> List[Category]:
    """Retrieve all categories ordered by name."""
    return db.session.query(Category).order_by(Category.name.asc()).all()


def get_category_by_id(category_id: str) -> Category:
    """Retrieve category by ID or raise NotFoundError."""
    cat = db.session.get(Category, category_id)
    if not cat:
        raise NotFoundError(message=f"Category with ID '{category_id}' not found.")
    return cat


def create_category(
    name: str,
    is_transfer: bool = False,
    color: Optional[str] = None,
) -> Category:
    """Create a new category. Raises ConflictError (409) if name exists."""
    clean_name = name.strip()
    if not clean_name:
        raise ValidationError(message="Category name cannot be empty.")

    existing = db.session.query(Category).filter(Category.name.ilike(clean_name)).first()
    if existing:
        raise ConflictError(message=f"Category '{clean_name}' already exists.")

    cat = Category(
        name=clean_name,
        is_system=False,
        is_transfer=is_transfer,
        is_active=True,
        color=color or "#6B7280",
    )
    db.session.add(cat)
    db.session.commit()
    return cat


def update_category(
    category_id: str,
    name: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_transfer: Optional[bool] = None,
    color: Optional[str] = None,
) -> Category:
    """Update category. System categories cannot be renamed."""
    cat = get_category_by_id(category_id)

    if name is not None:
        clean_name = name.strip()
        if cat.is_system and clean_name != cat.name:
            raise ValidationError(message="System categories cannot be renamed.")
        # Check duplicate name
        existing = (
            db.session.query(Category)
            .filter(Category.name.ilike(clean_name), Category.id != category_id)
            .first()
        )
        if existing:
            raise ConflictError(message=f"Category '{clean_name}' already exists.")
        cat.name = clean_name

    if is_active is not None:
        cat.is_active = is_active
    if is_transfer is not None:
        cat.is_transfer = is_transfer
    if color is not None:
        cat.color = color

    db.session.commit()
    return cat


def list_rules(category_id: Optional[str] = None) -> List[ClassificationRule]:
    """Retrieve classification rules, optionally filtered by category_id."""
    query = db.session.query(ClassificationRule).join(Category)
    if category_id:
        query = query.filter(ClassificationRule.category_id == category_id)
    return query.order_by(ClassificationRule.priority.desc(), ClassificationRule.keyword.asc()).all()


def get_rule_by_id(rule_id: str) -> ClassificationRule:
    """Retrieve rule by ID or raise NotFoundError."""
    rule = db.session.get(ClassificationRule, rule_id)
    if not rule:
        raise NotFoundError(message=f"Rule with ID '{rule_id}' not found.")
    return rule


def create_rule(
    category_id: str,
    keyword: str,
    match_type: str = "partial",
    priority: int = 100,
    direction: str = "any",
) -> ClassificationRule:
    """Create a new user-defined classification rule."""
    # Ensure category exists
    get_category_by_id(category_id)

    clean_kw = keyword.strip()
    if not clean_kw:
        raise ValidationError(message="Rule keyword cannot be empty.")

    if match_type not in ("exact", "partial", "regex"):
        raise ValidationError(message=f"Invalid match_type '{match_type}'. Must be exact, partial, or regex.")

    clean_dir = (direction or "any").strip().lower()
    if clean_dir not in ("any", "debit", "credit"):
        raise ValidationError(message="Invalid direction. Must be any, debit, or credit.")

    rule = ClassificationRule(
        category_id=category_id,
        keyword=clean_kw,
        match_type=match_type,
        priority=priority,
        direction=clean_dir,
        is_active=True,
        is_user_defined=True,
    )
    db.session.add(rule)
    db.session.commit()
    return rule


def update_rule(
    rule_id: str,
    category_id: Optional[str] = None,
    keyword: Optional[str] = None,
    match_type: Optional[str] = None,
    priority: Optional[int] = None,
    is_active: Optional[bool] = None,
    direction: Optional[str] = None,
) -> ClassificationRule:
    """Update rule fields."""
    rule = get_rule_by_id(rule_id)

    if category_id is not None:
        get_category_by_id(category_id)
        rule.category_id = category_id

    if keyword is not None:
        clean_kw = keyword.strip()
        if not clean_kw:
            raise ValidationError(message="Rule keyword cannot be empty.")
        rule.keyword = clean_kw

    if match_type is not None:
        if match_type not in ("exact", "partial", "regex"):
            raise ValidationError(message=f"Invalid match_type '{match_type}'. Must be exact, partial, or regex.")
        rule.match_type = match_type

    if priority is not None:
        rule.priority = priority

    if is_active is not None:
        rule.is_active = is_active

    if direction is not None:
        clean_dir = direction.strip().lower()
        if clean_dir not in ("any", "debit", "credit"):
            raise ValidationError(message="Invalid direction. Must be any, debit, or credit.")
        rule.direction = clean_dir

    db.session.commit()
    return rule


def delete_rule(rule_id: str) -> None:
    """Delete a user-defined rule. System rules cannot be deleted."""
    rule = get_rule_by_id(rule_id)
    if not rule.is_user_defined:
        raise ValidationError(message="System-defined rules cannot be deleted.")

    db.session.delete(rule)
    db.session.commit()

