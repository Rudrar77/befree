"""ClassificationRule model for keyword-based transaction categorization."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.models.category import Category


class MatchType(str, enum.Enum):
    """How the keyword should be matched per Appendix A3."""

    EXACT = "exact"
    PARTIAL = "partial"
    REGEX = "regex"


class ClassificationRule(db.Model):
    """Keyword-based rule for classifying transactions into categories."""

    __tablename__ = "classification_rules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    category_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    keyword: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    match_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=MatchType.PARTIAL.value
    )
    priority: Mapped[int] = mapped_column(nullable=False, default=100)
    direction: Mapped[str] = mapped_column(String(10), nullable=False, default="any")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    is_user_defined: Mapped[bool] = mapped_column(nullable=False, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    category: Mapped[Category] = relationship(
        "Category", back_populates="rules"
    )

    @property
    def category_name(self) -> str:
        return self.category.name if self.category else ""

    def to_dict(self) -> dict[str, Any]:
        """Convert rule to dict per Appendix A4."""
        return {
            "id": self.id,
            "category_id": self.category_id,
            "category_name": self.category_name,
            "keyword": self.keyword,
            "match_type": self.match_type,
            "priority": self.priority,
            "direction": self.direction or "any",
            "is_active": self.is_active,
            "is_user_defined": self.is_user_defined,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<ClassificationRule '{self.keyword}' → {self.category_id}>"
