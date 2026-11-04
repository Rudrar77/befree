"""ValidationResult model for statement validation findings."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.models.statement import Statement


class ValidationResult(db.Model):
    """Validation finding for a processed statement."""

    __tablename__ = "validation_results"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    statement_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("statements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    transaction_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    transaction_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    statement: Mapped[Statement] = relationship(
        "Statement", back_populates="validation_results"
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict matching Appendix A4 issue item."""
        return {
            "id": self.id,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "transaction_id": self.transaction_id,
            "transaction_description": self.transaction_description,
        }

    def __repr__(self) -> str:
        return f"<ValidationResult {self.code} [{self.severity}]>"
