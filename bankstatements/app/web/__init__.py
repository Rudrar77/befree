"""Web blueprint."""

from flask import Blueprint

web_bp = Blueprint(
    "web",
    __name__,
    template_folder="templates",
)

from app.web import routes  # noqa: E402, F401

