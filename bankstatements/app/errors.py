"""Application error classes and error handlers matching Appendix A2."""

from __future__ import annotations

from typing import Any, List, Optional
from flask import Flask, Response, jsonify, render_template, request
from werkzeug.exceptions import HTTPException


class AppError(Exception):
    """Base application error."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: Optional[str] = None,
        details: Optional[List[dict[str, Any]]] = None,
    ) -> None:
        super().__init__(message or self.message)
        if message is not None:
            self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        """Convert error to API error envelope per Appendix A2."""
        err: dict[str, Any] = {
            "code": self.error_code,
            "message": self.message,
        }
        if self.details is not None:
            err["details"] = self.details
        return {"error": err}


class ValidationError(AppError):
    status_code = 422
    error_code = "VALIDATION_ERROR"
    message = "Validation failed."


class InvalidFileType(AppError):
    status_code = 415
    error_code = "INVALID_FILE_TYPE"
    message = "Only PDF files are supported."


class InvalidPdfSignature(AppError):
    status_code = 400
    error_code = "INVALID_PDF_SIGNATURE"
    message = "File does not appear to be a valid PDF."


class FileTooLarge(AppError):
    status_code = 413
    error_code = "FILE_TOO_LARGE"
    message = "File exceeds the maximum allowed size."


class PdfCorrupted(AppError):
    status_code = 422
    error_code = "PDF_CORRUPTED"
    message = "PDF file is corrupted and cannot be processed."


class PdfPasswordProtected(AppError):
    status_code = 422
    error_code = "PDF_PASSWORD_PROTECTED"
    message = "Password-protected PDFs are not supported."


class NotFoundError(AppError):
    status_code = 404
    error_code = "NOT_FOUND"
    message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = 409
    error_code = "CONFLICT"
    message = "A conflict occurred with the current state of the resource."


class ProcessingFailed(AppError):
    status_code = 500
    error_code = "PROCESSING_FAILED"
    message = "Statement processing failed."


class InternalError(AppError):
    status_code = 500
    error_code = "INTERNAL_ERROR"
    message = "An unexpected internal error occurred."


def _is_api_request() -> bool:
    """Check if the current request is targeting the API."""
    return request.path.startswith("/api") or request.headers.get("Accept") == "application/json"


def _error_response(error: AppError) -> tuple[Response, int]:
    """Return JSON for API requests, HTML otherwise."""
    if _is_api_request():
        return jsonify(error.to_dict()), error.status_code
    return (
        Response(
            render_template(
                "errors/500.html" if error.status_code >= 500 else "errors/404.html",
                error_code=error.status_code,
                error_message=error.message,
            ),
            status=error.status_code,
            content_type="text/html",
        ),
        error.status_code,
    )


def register_error_handlers(app: Flask) -> None:
    """Register error handlers on the Flask app."""

    @app.errorhandler(AppError)
    def handle_app_error(error: AppError) -> tuple[Response, int]:
        app.logger.warning("AppError %s: %s", error.error_code, error.message)
        return _error_response(error)

    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException) -> tuple[Response, int]:
        code = error.code or 500
        if code == 404:
            return _error_response(NotFoundError(message=error.description))
        elif code == 413:
            return _error_response(FileTooLarge(message=error.description))
        elif code == 415:
            return _error_response(InvalidFileType(message=error.description))
        elif code == 400:
            return _error_response(ValidationError(message=error.description))
        elif code == 409:
            return _error_response(ConflictError(message=error.description))
        elif code == 422:
            return _error_response(ValidationError(message=error.description))
        return _error_response(InternalError(message=error.description))

    @app.errorhandler(Exception)
    def handle_exception(error: Exception) -> tuple[Response, int]:
        app.logger.exception("Unhandled server exception: %s", error)
        return _error_response(InternalError())
