"""API blueprint package."""

from flask import Blueprint

api_bp = Blueprint("api", __name__, url_prefix="/api")

# Import all route modules so endpoints register on api_bp
from app.api import (  # noqa: E402, F401
    analytics,
    categories,
    classification,
    classify,
    docs,
    export,
    health,
    statements,
    transactions,
    validation,
)
