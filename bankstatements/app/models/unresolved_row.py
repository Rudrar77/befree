"""UnresolvedRow model for rows that could not be parsed into transactions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.models.statement import Statement


class UnresolvedRow(db.Model):
    """A row extracted from a statement page that could not be parsed."""

    __tablename__ = "unresolved_rows"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    statement_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("statements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_page: Mapped[Optional[int]] = mapped_column(nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    extraction_method: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    statement: Mapped[Statement] = relationship(
        "Statement", back_populates="unresolved_rows"
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert unresolved row to dict per Appendix A4."""
        return {
            "id": self.id,
            "statement_id": self.statement_id,
            "source_page": self.source_page,
            "raw_text": self.raw_text,
            "reason": self.reason,
            "extraction_method": self.extraction_method,
        }

    def __repr__(self) -> str:
        return f"<UnresolvedRow page={self.source_page} reason='{self.reason}'>"
