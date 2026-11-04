"""Bank Statement Processing application factory."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from flask import Flask
from sqlalchemy import event, inspect, text

from app.config import config_by_name
from app.errors import register_error_handlers
from app.extensions import csrf, db, executor, migrate
from app.security import LogRedactionFilter, apply_security_headers
from app.web.filters import format_inr, iso_to_display, status_badge


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask application factory.

    Args:
        config_name: 'development', 'testing', or 'production'.

    Returns:
        Configured Flask application instance.
    """
    if config_name is None:
        config_name = os.environ.get("FLASK_CONFIG", "development")

    flask_app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="web/templates",
        static_folder="web/static",
    )

    # Load configuration
    config_class = config_by_name.get(config_name, config_by_name["default"])
    flask_app.config.from_object(config_class)

    # Ensure instance and upload directories exist
    Path(flask_app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(flask_app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)

    # Logging setup
    log_level = getattr(logging, flask_app.config.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    flask_app.logger.setLevel(log_level)
    redaction_filter = LogRedactionFilter()
    for handler in logging.root.handlers:
        handler.addFilter(redaction_filter)
    flask_app.logger.addFilter(redaction_filter)

    # Initialize extensions
    db.init_app(flask_app)
    migrate.init_app(flask_app, db)
    csrf.init_app(flask_app)
    executor.init_app(flask_app)

    # Import models so they are registered with SQLAlchemy, then create tables
    with flask_app.app_context():
        from app import models as _models  # noqa: F401

        db.create_all()
        existing_transaction_columns = {
            column["name"] for column in inspect(db.engine).get_columns("transactions")
        }
        extraction_columns = {
            "transaction_id": "VARCHAR(100)",
            "mode": "VARCHAR(100)",
            "currency": "VARCHAR(10)",
            "original_amount_text": "TEXT",
            "source_row": "INTEGER",
            "extraction_confidence": "FLOAT",
        }
        with db.engine.begin() as connection:
            for column_name, column_type in extraction_columns.items():
                if column_name not in existing_transaction_columns:
                    connection.execute(text(
                        f"ALTER TABLE transactions ADD COLUMN {column_name} {column_type}"
                    ))
        if not flask_app.config.get("TESTING"):
            from app.cli import ensure_classification_schema, seed_default_data

            ensure_classification_schema()
            seed_default_data(echo=False)

    # SQLite pragmas: foreign_keys=ON, WAL mode (for file-based sqlite)
    with flask_app.app_context():
        if db.engine.dialect.name == "sqlite":
            @event.listens_for(db.engine, "connect")
            def _set_sqlite_pragmas(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
                try:
                    cursor = dbapi_connection.cursor()
                    cursor.execute("PRAGMA foreign_keys=ON")
                    # WAL mode only for file databases, ignored in memory
                    if not flask_app.config.get("TESTING"):
                        cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.close()
                except Exception:
                    pass

    # Register custom Jinja filters
    flask_app.jinja_env.filters["inr"] = format_inr
    flask_app.jinja_env.filters["iso_to_display"] = iso_to_display
    flask_app.jinja_env.filters["status_badge"] = status_badge

    # Register blueprints
    from app.api import api_bp
    from app.web import web_bp

    flask_app.register_blueprint(api_bp)
    flask_app.register_blueprint(web_bp)

    # Register error handlers (JSON for /api, HTML elsewhere)
    register_error_handlers(flask_app)

    # Security headers
    apply_security_headers(flask_app)

    # CLI commands
    from app.cli import register_cli_commands
    register_cli_commands(flask_app)

    if hasattr(config_class, "init_app"):
        config_class.init_app(flask_app)

    flask_app.logger.info("Application initialized with config: %s", config_name)
    return flask_app
