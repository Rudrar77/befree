"""Excel (.xlsx) exporter using OpenPyXL with multi-sheet structure and formula injection protection."""

from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill


def sanitize_text(value: Any) -> str:
    """Sanitize text to prevent formula injection."""
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


def export_statement_to_excel(
    statement: Any,
    transactions: List[Any],
    validation_issues: List[Any],
    reconciliation: Optional[dict[str, Any]] = None,
    analytics: Optional[dict[str, Any]] = None,
) -> io.BytesIO:
    """Generate professional multi-sheet Excel workbook.

    Sheets:
        1. Account Info
        2. Transactions
        3. Category Summary
        4. Monthly Summary
        5. Validation Report
    """
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    num_format = "#,##0.00"

    # -------------------------------------------------------------
    # Sheet 1: Account Info
    # -------------------------------------------------------------
    ws_info = wb.create_sheet(title="Account Info")
    ws_info.append(["Field", "Value"])
    ws_info["A1"].font = header_font
    ws_info["A1"].fill = header_fill
    ws_info["B1"].font = header_font
    ws_info["B1"].fill = header_fill

    info_rows = [
        ("Statement ID", statement.id if hasattr(statement, "id") else ""),
        ("Original Filename", statement.original_filename if hasattr(statement, "original_filename") else ""),
        ("Bank Name", statement.bank_name if hasattr(statement, "bank_name") else "Not found"),
        ("Account Holder", statement.account_holder_name if hasattr(statement, "account_holder_name") else "Not found"),
        ("Masked Account Number", statement.account_number_masked if hasattr(statement, "account_number_masked") else "Not found"),
        ("IFSC Code", statement.ifsc if hasattr(statement, "ifsc") else "Not found"),
        ("Branch", statement.branch_name if hasattr(statement, "branch_name") else "Not found"),
        ("Period Start", str(statement.period_start) if hasattr(statement, "period_start") and statement.period_start else "Not found"),
        ("Period End", str(statement.period_end) if hasattr(statement, "period_end") and statement.period_end else "Not found"),
        ("Opening Balance", float(statement.opening_balance) if hasattr(statement, "opening_balance") and statement.opening_balance is not None else "Not found"),
        ("Closing Balance", float(statement.closing_balance) if hasattr(statement, "closing_balance") and statement.closing_balance is not None else "Not found"),
        ("Total Transactions", statement.transaction_count if hasattr(statement, "transaction_count") else len(transactions)),
        ("Processing Status", statement.processing_status if hasattr(statement, "processing_status") else ""),
    ]

    for label, val in info_rows:
        ws_info.append([label, sanitize_text(val) if isinstance(val, str) else val])

    ws_info.column_dimensions["A"].width = 25
    ws_info.column_dimensions["B"].width = 40

    # -------------------------------------------------------------
    # Sheet 2: Transactions
    # -------------------------------------------------------------
    ws_txn = wb.create_sheet(title="Transactions")
    txn_headers = [
        "Transaction Date",
        "Description",
        "Debit (₹)",
        "Credit (₹)",
        "Balance (₹)",
        "Category",
        "Method",
        "Confidence",
        "Validation Status",
        "Reference Number",
    ]
    ws_txn.append(txn_headers)
    for col_idx in range(1, len(txn_headers) + 1):
        cell = ws_txn.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill

    for row_idx, t in enumerate(transactions, start=2):
        t_date = t.transaction_date if hasattr(t, "transaction_date") else t.get("transaction_date")
        desc = t.description if hasattr(t, "description") else t.get("description", "")
        debit = float(t.debit) if hasattr(t, "debit") and t.debit is not None else None
        credit = float(t.credit) if hasattr(t, "credit") and t.credit is not None else None
        balance = float(t.balance) if hasattr(t, "balance") and t.balance is not None else None
        category = t.category_name if hasattr(t, "category_name") else t.get("category_name", "Uncategorized")
        method = t.classification_method if hasattr(t, "classification_method") else t.get("classification_method", "none")
        confidence = float(t.confidence) if hasattr(t, "confidence") and t.confidence is not None else None
        val_status = t.validation_status if hasattr(t, "validation_status") else t.get("validation_status", "valid")
        ref_num = t.reference_number if hasattr(t, "reference_number") else t.get("reference_number", "")

        ws_txn.append([
            t_date,
            sanitize_text(desc),
            debit,
            credit,
            balance,
            sanitize_text(category),
            sanitize_text(method),
            confidence,
            sanitize_text(val_status),
            sanitize_text(ref_num),
        ])

        # Apply formatting to numeric cells
        if debit is not None:
            ws_txn.cell(row=row_idx, column=3).number_format = num_format
        if credit is not None:
            ws_txn.cell(row=row_idx, column=4).number_format = num_format
        if balance is not None:
            ws_txn.cell(row=row_idx, column=5).number_format = num_format
        if confidence is not None:
            ws_txn.cell(row=row_idx, column=8).number_format = "0.0%"

    ws_txn.column_dimensions["A"].width = 16
    ws_txn.column_dimensions["B"].width = 40
    ws_txn.column_dimensions["C"].width = 15
    ws_txn.column_dimensions["D"].width = 15
    ws_txn.column_dimensions["E"].width = 15
    ws_txn.column_dimensions["F"].width = 20
    ws_txn.column_dimensions["G"].width = 12
    ws_txn.column_dimensions["H"].width = 12
    ws_txn.column_dimensions["I"].width = 16
    ws_txn.column_dimensions["J"].width = 20

    # -------------------------------------------------------------
    # Sheet 3: Category Summary
    # -------------------------------------------------------------
    ws_cat = wb.create_sheet(title="Category Summary")
    ws_cat.append(["Category", "Total Expenditure (₹)", "Transaction Count"])
    for col_idx in range(1, 4):
        cell = ws_cat.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill

    if analytics and "category_expenditure" in analytics:
        for r_idx, c_item in enumerate(analytics["category_expenditure"], start=2):
            tot = float(Decimal(str(c_item.get("total", "0.00"))))
            cnt = int(c_item.get("count", 0))
            ws_cat.append([sanitize_text(c_item.get("category_name")), tot, cnt])
            ws_cat.cell(row=r_idx, column=2).number_format = num_format

    ws_cat.column_dimensions["A"].width = 25
    ws_cat.column_dimensions["B"].width = 22
    ws_cat.column_dimensions["C"].width = 18

    # -------------------------------------------------------------
    # Sheet 4: Monthly Summary
    # -------------------------------------------------------------
    ws_mon = wb.create_sheet(title="Monthly Summary")
    ws_mon.append(["Month", "Total Income (₹)", "Total Expenses (₹)", "Net Cash Flow (₹)"])
    for col_idx in range(1, 5):
        cell = ws_mon.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill

    if analytics and "monthly" in analytics:
        for r_idx, m_item in enumerate(analytics["monthly"], start=2):
            inc = float(Decimal(str(m_item.get("income", "0.00"))))
            exp = float(Decimal(str(m_item.get("expenses", "0.00"))))
            net = inc - exp
            ws_mon.append([sanitize_text(m_item.get("month")), inc, exp, net])
            ws_mon.cell(row=r_idx, column=2).number_format = num_format
            ws_mon.cell(row=r_idx, column=3).number_format = num_format
            ws_mon.cell(row=r_idx, column=4).number_format = num_format

    ws_mon.column_dimensions["A"].width = 15
    ws_mon.column_dimensions["B"].width = 20
    ws_mon.column_dimensions["C"].width = 20
    ws_mon.column_dimensions["D"].width = 20

    # -------------------------------------------------------------
    # Sheet 5: Validation Report
    # -------------------------------------------------------------
    ws_val = wb.create_sheet(title="Validation Report")
    ws_val.append(["Severity", "Code", "Message", "Transaction ID", "Transaction Description"])
    for col_idx in range(1, 6):
        cell = ws_val.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill

    for issue in validation_issues:
        sev = issue.severity if hasattr(issue, "severity") else issue.get("severity", "")
        code = issue.code if hasattr(issue, "code") else issue.get("code", "")
        msg = issue.message if hasattr(issue, "message") else issue.get("message", "")
        t_id = issue.transaction_id if hasattr(issue, "transaction_id") else issue.get("transaction_id", "")
        t_desc = issue.transaction_description if hasattr(issue, "transaction_description") else issue.get("transaction_description", "")
        ws_val.append([
            sanitize_text(sev),
            sanitize_text(code),
            sanitize_text(msg),
            sanitize_text(t_id or ""),
            sanitize_text(t_desc or ""),
        ])

    ws_val.column_dimensions["A"].width = 12
    ws_val.column_dimensions["B"].width = 25
    ws_val.column_dimensions["C"].width = 45
    ws_val.column_dimensions["D"].width = 38
    ws_val.column_dimensions["E"].width = 30

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output

