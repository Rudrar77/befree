"""Transaction model for individual bank statement entries matching Appendix A."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.types import Money

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.statement import Statement


class Transaction(db.Model):
    """Individual transaction extracted from a bank statement."""

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_stmt_date", "statement_id", "transaction_date"),
        Index("ix_transactions_category", "category_id"),
        Index("ix_transactions_needs_review", "needs_review"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    statement_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("statements.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Transaction details
    transaction_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    original_description: Mapped[str] = mapped_column(Text, nullable=False)

    # Amounts: debit and credit are non-negative, sign carried by field
    debit: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)
    credit: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)
    balance: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)

    reference_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    mode: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    original_amount_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_row: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extraction_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Classification
    category_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    classification_method: Mapped[str] = mapped_column(
        String(20), nullable=False, default="none"
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    applied_rule_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    manual_override: Mapped[bool] = mapped_column(nullable=False, default=False)
    needs_review: Mapped[bool] = mapped_column(nullable=False, default=False)

    # Duplicates & Validation
    duplicate_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="none"
    )
    duplicate_of: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    validation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="valid"
    )

    # JSON stored fields
    _anomaly_flags: Mapped[Optional[str]] = mapped_column("anomaly_flags", Text, nullable=True)
    _warnings: Mapped[Optional[str]] = mapped_column("warnings", Text, nullable=True)

    # Extraction info
    source_page: Mapped[Optional[int]] = mapped_column(nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    statement: Mapped[Statement] = relationship(
        "Statement", back_populates="transactions"
    )
    category: Mapped[Optional[Category]] = relationship(
        "Category", back_populates="transactions"
    )

    @property
    def anomaly_flags(self) -> list[dict[str, Any]]:
        """Return parsed anomaly flags."""
        if not self._anomaly_flags:
            return []
        try:
            return json.loads(self._anomaly_flags)
        except Exception:
            return []

    @anomaly_flags.setter
    def anomaly_flags(self, val: list[dict[str, Any]] | str | None) -> None:
        if val is None:
            self._anomaly_flags = "[]"
        elif isinstance(val, str):
            self._anomaly_flags = val
        else:
            self._anomaly_flags = json.dumps(val)

    @property
    def warnings(self) -> list[str]:
        """Return parsed warnings."""
        if not self._warnings:
            return []
        try:
            return json.loads(self._warnings)
        except Exception:
            return []

    @warnings.setter
    def warnings(self, val: list[str] | str | None) -> None:
        if val is None:
            self._warnings = "[]"
        elif isinstance(val, str):
            self._warnings = val
        else:
            self._warnings = json.dumps(val)

    @property
    def category_name(self) -> str:
        """Category name for API response."""
        if self.category:
            return self.category.name
        return "Unclassified"

    def to_dict(self) -> dict[str, Any]:
        """Convert transaction to dictionary matching Appendix A4."""
        return {
            "id": self.id,
            "statement_id": self.statement_id,
            "transaction_date": self.transaction_date.isoformat() if self.transaction_date else None,
            "description": self.description,
            "original_description": self.original_description,
            "debit": f"{self.debit:.2f}" if self.debit is not None else None,
            "credit": f"{self.credit:.2f}" if self.credit is not None else None,
            "balance": f"{self.balance:.2f}" if self.balance is not None else None,
            "reference_number": self.reference_number,
            "transaction_id": self.transaction_id,
            "mode": self.mode,
            "currency": self.currency,
            "original_amount_text": self.original_amount_text,
            "source_row": self.source_row,
            "extraction_confidence": self.extraction_confidence,
            "category_id": self.category_id,
            "category_name": self.category_name,
            "classification_method": self.classification_method,
            "confidence": round(self.confidence, 4) if self.confidence is not None else None,
            "applied_rule_id": self.applied_rule_id,
            "model_version": self.model_version,
            "manual_override": self.manual_override,
            "needs_review": self.needs_review,
            "duplicate_status": self.duplicate_status,
            "duplicate_of": self.duplicate_of,
            "validation_status": self.validation_status,
            "anomaly_flags": self.anomaly_flags,
            "source_page": self.source_page,
            "extraction_method": self.extraction_method,
            "warnings": self.warnings,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def __repr__(self) -> str:
        amt = f"D:{self.debit}" if self.debit else f"C:{self.credit}"
        return f"<Transaction {self.id} {amt}>"
