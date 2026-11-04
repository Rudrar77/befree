"""Health check endpoint."""

from flask import jsonify

from app.api import api_bp


@api_bp.route("/health", methods=["GET"])
def health_check():  # type: ignore[no-untyped-def]
    """GET /api/health → returns service health status."""
    return jsonify({"status": "ok"})

