"""Category model for transaction classification."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.models.classification_rule import ClassificationRule
    from app.models.transaction import Transaction


class Category(db.Model):
    """Transaction category for classification."""

    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    is_system: Mapped[bool] = mapped_column(nullable=False, default=True)
    is_transfer: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True, default="#6B7280")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    transactions: Mapped[list[Transaction]] = relationship(
        "Transaction", back_populates="category", lazy="dynamic"
    )
    rules: Mapped[list[ClassificationRule]] = relationship(
        "ClassificationRule", back_populates="category", cascade="all, delete-orphan", lazy="dynamic"
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert category to dict per Appendix A4."""
        return {
            "id": self.id,
            "name": self.name,
            "is_system": self.is_system,
            "is_transfer": self.is_transfer,
            "is_active": self.is_active,
            "color": self.color,
        }

    def __repr__(self) -> str:
        return f"<Category {self.name}>"
