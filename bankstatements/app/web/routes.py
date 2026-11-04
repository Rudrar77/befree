"""Web routes for the HTML user interface and Swagger documentation."""

from __future__ import annotations

from typing import Any
from flask import render_template, render_template_string
from app.api.docs import SWAGGER_UI_HTML
from app.services.statement_service import get_statement_by_id
from app.web import web_bp


@web_bp.route("/")
def dashboard() -> Any:
    """Dashboard overview page."""
    return render_template("dashboard.html")


@web_bp.route("/statements")
def statements() -> Any:
    """Statements listing and upload page."""
    return render_template("statements.html")


@web_bp.route("/statements/<uuid:statement_id>")
def statement_detail(statement_id: Any) -> Any:
    """Statement detail page with server-rendered initial shell."""
    stmt = get_statement_by_id(str(statement_id))
    return render_template("statement_detail.html", statement=stmt)


@web_bp.route("/transactions")
def transactions() -> Any:
    """Transactions listing and filtering page."""
    return render_template("transactions.html")


@web_bp.route("/categories")
def categories() -> Any:
    """Categories and classification rules management page."""
    return render_template("categories.html")


@web_bp.route("/docs")
def swagger_docs() -> Any:
    """Interactive Swagger UI API documentation matching Appendix A."""
    return render_template_string(SWAGGER_UI_HTML)
