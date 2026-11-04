"""Application configuration classes."""

import os
from decimal import Decimal
from pathlib import Path
from sqlalchemy.pool import StaticPool


BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    """Base configuration."""

    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

    # Database
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'bankstatements.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        "connect_args": {"check_same_thread": False},
    }

    # File uploads
    UPLOAD_DIR: str = os.environ.get("UPLOAD_DIR", str(BASE_DIR / "uploads"))
    MAX_UPLOAD_MB: int = int(os.environ.get("MAX_UPLOAD_MB", "50"))
    MAX_CONTENT_LENGTH: int = MAX_UPLOAD_MB * 1024 * 1024

    # File retention
    FILE_RETENTION_DAYS: int = int(os.environ.get("FILE_RETENTION_DAYS", "90"))

    # OCR settings
    OCR_DPI: int = int(os.environ.get("OCR_DPI", "300"))
    TEXT_MIN_CHARS_PER_PAGE: int = int(os.environ.get("TEXT_MIN_CHARS_PER_PAGE", "50"))
    OCR_PROVIDER: str = os.environ.get("OCR_PROVIDER", "paddleocr")
    OCR_FALLBACK_PROVIDER: str = os.environ.get("OCR_FALLBACK_PROVIDER", "tesseract").strip()
    OCR_SECONDARY_PROVIDER: str = os.environ.get("OCR_SECONDARY_PROVIDER", "").strip()
    OCR_USE_GPU: bool = os.environ.get("OCR_USE_GPU", "false").strip().lower() in {"1", "true", "yes"}
    MAX_DOCUMENT_PAGES: int = int(os.environ.get("MAX_DOCUMENT_PAGES", "500"))
    OCR_IMAGE_COVERAGE_THRESHOLD: float = float(
        os.environ.get("OCR_IMAGE_COVERAGE_THRESHOLD", "0.20")
    )

    # Processing thresholds
    CONFIDENCE_THRESHOLD: Decimal = Decimal(os.environ.get("CONFIDENCE_THRESHOLD", "0.6"))
    RECONCILIATION_TOLERANCE: Decimal = Decimal(os.environ.get("RECONCILIATION_TOLERANCE", "0.50"))

    # Background processing
    STALE_JOB_MINUTES: int = int(os.environ.get("STALE_JOB_MINUTES", "30"))
    WORKER_THREADS: int = int(os.environ.get("WORKER_THREADS", "2"))

    # CORS
    CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "http://localhost:5000")

    # ML model
    MODEL_PATH: str = os.environ.get("MODEL_PATH", str(BASE_DIR / "models" / "classifier.pkl"))
    PRETRAINED_TRANSACTION_MODEL_PATH: str = os.environ.get(
        "PRETRAINED_TRANSACTION_MODEL_PATH",
        str(BASE_DIR / "app" / "data" / "transaction_classifier_v3.joblib"),
    )
    PRETRAINED_TRANSACTION_MODEL_SHA256: str = os.environ.get(
        "PRETRAINED_TRANSACTION_MODEL_SHA256",
        "63f7cffc114dd72572374db6f17f88aa35219b8514335263d1ded1fe62a31fd6",
    )
    PRETRAINED_TRANSACTION_CONFIDENCE_THRESHOLD: float = float(
        os.environ.get("PRETRAINED_TRANSACTION_CONFIDENCE_THRESHOLD", "0.30")
    )

    # Logging
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

    # CSRF
    WTF_CSRF_ENABLED: bool = True
    WTF_CSRF_TIME_LIMIT: int = 3600


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG: bool = True
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "DEBUG")


class TestingConfig(Config):
    """Testing configuration."""

    TESTING: bool = True
    SQLALCHEMY_DATABASE_URI: str = "sqlite://"
    WTF_CSRF_ENABLED: bool = False
    UPLOAD_DIR: str = str(BASE_DIR / "test_uploads")
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG: bool = False
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "WARNING")

    @classmethod
    def init_app(cls, app):  # type: ignore[no-untyped-def]
        """Production-specific initialization."""
        assert app.config["SECRET_KEY"] != "dev-secret-key-change-in-production", (
            "SECRET_KEY must be set in production!"
        )


config_by_name: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
