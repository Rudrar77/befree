"""Security middleware, filename sanitizing, log redaction, and account masking."""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from flask import Flask, Response


def apply_security_headers(app: Flask) -> None:
    """Register after_request handler that sets security headers on every response."""

    @app.after_request
    def set_security_headers(response: Response) -> Response:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal."""
    filename = unicodedata.normalize("NFKD", filename)
    filename = filename.encode("ascii", "ignore").decode("ascii")
    filename = os.path.basename(filename)
    filename = filename.replace("\x00", "").replace("/", "_").replace("\\", "_")
    filename = re.sub(r"[^\w.\-]", "_", filename)
    filename = filename.lstrip(".")
    filename = re.sub(r"_+", "_", filename)
    name, ext = os.path.splitext(filename)
    if len(name) > 150:
        name = name[:150]
    filename = name + ext
    if not filename or filename == ext:
        filename = "statement" + ext
    return filename


def mask_account_number(account_number: str | None) -> str:
    """Mask account number showing only last 4 digits per Appendix A1: 'XXXXXX1234'."""
    if not account_number:
        return ""
    digits = re.sub(r"\D", "", str(account_number))
    if len(digits) <= 4:
        return f"XXXXXX{digits}"
    last4 = digits[-4:]
    return f"XXXXXX{last4}"


class LogRedactionFilter(logging.Filter):
    """Logging filter that redacts account numbers and sensitive info."""

    ACCOUNT_PATTERN = re.compile(r"\b\d{9,18}\b")
    IFSC_PATTERN = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.ACCOUNT_PATTERN.sub("[ACCOUNT_REDACTED]", record.msg)
            record.msg = self.IFSC_PATTERN.sub("[IFSC_REDACTED]", record.msg)
        if record.args:
            new_args = []
            for arg in record.args if isinstance(record.args, tuple) else (record.args,):
                if isinstance(arg, str):
                    arg = self.ACCOUNT_PATTERN.sub("[ACCOUNT_REDACTED]", arg)
                    arg = self.IFSC_PATTERN.sub("[IFSC_REDACTED]", arg)
                new_args.append(arg)
            record.args = tuple(new_args)
        return True
