"""Statement model for bank statement processing matching Appendix A."""

from __future__ import annotations

import enum
import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Date, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.types import Money

if TYPE_CHECKING:
    from app.models.processing_log import ProcessingLog
    from app.models.transaction import Transaction
    from app.models.unresolved_row import UnresolvedRow
    from app.models.validation_result import ValidationResult


class PdfType(str, enum.Enum):
    """Type of PDF detected during processing per Appendix A3."""

    TEXT = "text"
    SCANNED = "scanned"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ProcessingStatus(str, enum.Enum):
    """Processing status per Appendix A3."""

    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"


class Statement(db.Model):
    """Bank statement model representing an uploaded and processed PDF."""

    __tablename__ = "statements"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_size_bytes: Mapped[int] = mapped_column(nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    page_count: Mapped[Optional[int]] = mapped_column(nullable=True)

    # PDF type per Appendix A3
    pdf_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PdfType.UNKNOWN.value
    )

    # Processing state per Appendix A3
    processing_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ProcessingStatus.UPLOADED.value, index=True
    )
    current_step: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    progress_percent: Mapped[int] = mapped_column(nullable=False, default=0)
    pages_total: Mapped[Optional[int]] = mapped_column(nullable=True)
    pages_done: Mapped[int] = mapped_column(nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Extracted metadata
    bank_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    account_holder_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    account_number_masked: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ifsc: Mapped[Optional[str]] = mapped_column(String(11), nullable=True)
    branch_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Balances (stored as paise, loaded as Decimal)
    opening_balance: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)
    closing_balance: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)

    # Summary counts
    transaction_count: Mapped[int] = mapped_column(nullable=False, default=0)
    unresolved_count: Mapped[int] = mapped_column(nullable=False, default=0)
    needs_review: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)

    # JSON field for page extraction methods: [{"page": 1, "method": "text", "ocr_used": false, "error": null}]
    _page_methods: Mapped[Optional[str]] = mapped_column("page_methods", Text, nullable=True)

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
    transactions: Mapped[list[Transaction]] = relationship(
        "Transaction",
        back_populates="statement",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    processing_logs: Mapped[list[ProcessingLog]] = relationship(
        "ProcessingLog",
        back_populates="statement",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    validation_results: Mapped[list[ValidationResult]] = relationship(
        "ValidationResult",
        back_populates="statement",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    unresolved_rows: Mapped[list[UnresolvedRow]] = relationship(
        "UnresolvedRow",
        back_populates="statement",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    @property
    def page_methods(self) -> list[dict[str, Any]]:
        """Return parsed page_methods list."""
        if not self._page_methods:
            return []
        try:
            return json.loads(self._page_methods)
        except Exception:
            return []

    @page_methods.setter
    def page_methods(self, val: list[dict[str, Any]] | str | None) -> None:
        """Set page_methods as JSON string."""
        if val is None:
            self._page_methods = "[]"
        elif isinstance(val, str):
            self._page_methods = val
        else:
            self._page_methods = json.dumps(val)

    def to_dict(self) -> dict[str, Any]:
        """Convert statement to dictionary matching Appendix A4."""
        return {
            "id": self.id,
            "original_filename": self.original_filename,
            "file_size_bytes": self.file_size_bytes,
            "page_count": self.page_count,
            "pdf_type": self.pdf_type,
            "processing_status": self.processing_status,
            "error_message": self.error_message,
            "bank_name": self.bank_name,
            "account_holder_name": self.account_holder_name,
            "account_number_masked": self.account_number_masked,
            "ifsc": self.ifsc,
            "branch_name": self.branch_name,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "opening_balance": f"{self.opening_balance:.2f}" if self.opening_balance is not None else None,
            "closing_balance": f"{self.closing_balance:.2f}" if self.closing_balance is not None else None,
            "transaction_count": self.transaction_count,
            "unresolved_count": self.unresolved_count,
            "page_methods": self.page_methods,
            "needs_review": self.needs_review,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def to_status_dict(self) -> dict[str, Any]:
        """Convert to ProcessingStatus dict per Appendix A4."""
        return {
            "statement_id": self.id,
            "processing_status": self.processing_status,
            "progress_percent": self.progress_percent,
            "current_step": self.current_step,
            "pages_total": self.pages_total,
            "pages_done": self.pages_done,
            "error_message": self.error_message,
            "updated_at": self.updated_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<Statement {self.id} [{self.processing_status}]>"
