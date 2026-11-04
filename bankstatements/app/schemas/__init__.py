"""Pydantic v2 schemas matching Appendix A exactly."""

from __future__ import annotations

from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Error schema (Appendix A2)
# ---------------------------------------------------------------------------

class ErrorIssue(BaseModel):
    """Specific field issue."""
    field: Optional[str] = None
    issue: str


class ErrorObject(BaseModel):
    """Inner error object."""
    code: str
    message: str
    details: Optional[List[dict[str, Any]]] = None


class ErrorEnvelope(BaseModel):
    """Top-level error envelope per Appendix A2."""
    error: ErrorObject


# ---------------------------------------------------------------------------
# Statement schema (Appendix A4)
# ---------------------------------------------------------------------------

class PageMethod(BaseModel):
    page: int
    method: str
    ocr_used: bool = False
    error: Optional[str] = None


class StatementSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    file_size_bytes: int
    page_count: Optional[int] = None
    pdf_type: str = "unknown"
    processing_status: str = "uploaded"
    bank_name: Optional[str] = None
    account_holder_name: Optional[str] = None
    account_number_masked: Optional[str] = None
    ifsc: Optional[str] = None
    branch_name: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    opening_balance: Optional[str] = None
    closing_balance: Optional[str] = None
    transaction_count: int = 0
    unresolved_count: int = 0
    page_methods: List[dict[str, Any]] = Field(default_factory=list)
    needs_review: bool = False
    created_at: str
    updated_at: str


class ProcessingStatusSchema(BaseModel):
    statement_id: str
    processing_status: str
    progress_percent: int = 0
    current_step: Optional[str] = None
    pages_total: Optional[int] = None
    pages_done: int = 0
    error_message: Optional[str] = None
    updated_at: str


# ---------------------------------------------------------------------------
# Transaction schema (Appendix A4)
# ---------------------------------------------------------------------------

class AnomalyFlag(BaseModel):
    type: str
    detail: str


class TransactionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    statement_id: str
    transaction_date: Optional[str] = None
    description: str
    original_description: str
    debit: Optional[str] = None
    credit: Optional[str] = None
    balance: Optional[str] = None
    reference_number: Optional[str] = None
    transaction_id: Optional[str] = None
    mode: Optional[str] = None
    currency: Optional[str] = None
    original_amount_text: Optional[str] = None
    source_row: Optional[int] = None
    extraction_confidence: Optional[float] = None
    category_id: Optional[str] = None
    category_name: str = "Uncategorized"
    classification_method: str = "none"
    confidence: Optional[float] = None
    applied_rule_id: Optional[str] = None
    model_version: Optional[str] = None
    manual_override: bool = False
    needs_review: bool = False
    duplicate_status: str = "none"
    duplicate_of: Optional[str] = None
    validation_status: str = "valid"
    anomaly_flags: List[dict[str, Any]] = Field(default_factory=list)
    source_page: Optional[int] = None
    extraction_method: str = "text"
    warnings: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Unresolved Row schema (Appendix A4)
# ---------------------------------------------------------------------------

class UnresolvedRowSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    statement_id: str
    source_page: Optional[int] = None
    raw_text: str
    reason: str
    extraction_method: Optional[str] = None


# ---------------------------------------------------------------------------
# Category & Rule schemas (Appendix A4)
# ---------------------------------------------------------------------------

class CategorySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    is_system: bool
    is_transfer: bool
    is_active: bool
    color: Optional[str] = None


class RuleSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    category_id: str
    category_name: str
    keyword: str
    match_type: str
    priority: int
    is_active: bool
    is_user_defined: bool
    created_at: str


# ---------------------------------------------------------------------------
# Validation Report schema (Appendix A4)
# ---------------------------------------------------------------------------

class ValidationIssue(BaseModel):
    id: str
    severity: str
    code: str
    message: str
    transaction_id: Optional[str] = None
    transaction_description: Optional[str] = None


class ReconciliationDetail(BaseModel):
    status: str
    opening_balance: Optional[str] = None
    total_credits: str
    total_debits: str
    expected_closing_balance: Optional[str] = None
    actual_closing_balance: Optional[str] = None
    difference: Optional[str] = None
    tolerance: str = "0.01"
    notes: List[str] = Field(default_factory=list)


class DuplicateSummary(BaseModel):
    exact: int = 0
    possible: int = 0


class AnomalySummary(BaseModel):
    flagged: int = 0


class ValidationReportSchema(BaseModel):
    statement_id: str
    overall_status: str
    issues: List[ValidationIssue] = Field(default_factory=list)
    reconciliation: ReconciliationDetail
    duplicate_summary: DuplicateSummary
    anomaly_summary: AnomalySummary
    checked_at: str


# ---------------------------------------------------------------------------
# Analytics schema (Appendix A4)
# ---------------------------------------------------------------------------

class HighTransaction(BaseModel):
    transaction_id: str
    amount: str
    description: str
    date: Optional[str] = None


class CategoryExpenditure(BaseModel):
    category_id: Optional[str] = None
    category_name: str
    total: str
    count: int


class MonthlyFigure(BaseModel):
    month: str
    income: str
    expenses: str


class DebitCreditDist(BaseModel):
    debit_count: int
    credit_count: int
    debit_total: str
    credit_total: str


class DailyCount(BaseModel):
    date: str
    count: int


class AnalyticsSchema(BaseModel):
    scope: str
    statement_id: Optional[str] = None
    total_income: str
    total_expenses: str
    net_cash_flow: str
    transfers_in: str
    transfers_out: str
    average_transaction_amount: Optional[str] = None
    highest_debit: Optional[HighTransaction] = None
    highest_credit: Optional[HighTransaction] = None
    category_expenditure: List[CategoryExpenditure] = Field(default_factory=list)
    monthly: List[MonthlyFigure] = Field(default_factory=list)
    debit_credit_distribution: DebitCreditDist
    daily_transaction_counts: List[DailyCount] = Field(default_factory=list)
    unclassified_count: int


# ---------------------------------------------------------------------------
# Paginated response per Appendix A1
# ---------------------------------------------------------------------------

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
