"""Upload service for secure file ingestion and validation."""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any, Tuple
import pymupdf as fitz
from PIL import Image
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.errors import (
    AppError,
    FileTooLarge,
    InvalidFileType,
    InvalidPdfSignature,
    PdfCorrupted,
    PdfInvalidPassword,
    PdfPasswordProtected,
)
from app.extensions import db
from app.models.statement import PdfType, ProcessingStatus, Statement

def validate_and_save_upload(
    file_storage: FileStorage,
    upload_dir: str,
    max_mb: int = 16,
    max_pages: int = 500,
    password: str | None = None,
) -> Tuple[Statement, None]:
    """Validate and persist PDF or image uploads securely."""
    raw_filename = file_storage.filename or "unknown.pdf"
    clean_display_name = secure_filename(raw_filename)
    if not clean_display_name:
        clean_display_name = "statement.pdf"

    _, ext = os.path.splitext(clean_display_name.lower())
    is_pdf = ext == ".pdf"
    is_image = ext in {".jpg", ".jpeg", ".png"}

    if not (is_pdf or is_image):
        raise InvalidFileType(
            message=f"File '{raw_filename}' is not a PDF.",
            details=[{"field": "file", "issue": "Supported formats are PDF, JPG, JPEG, and PNG."}],
        )

    stmt_id = str(uuid.uuid4())
    os.makedirs(upload_dir, exist_ok=True)
    stored_path = os.path.join(upload_dir, f"{stmt_id}{ext}")

    file_storage.seek(0)
    hasher = hashlib.sha256()
    total_bytes = 0
    max_bytes = max_mb * 1024 * 1024

    magic_header = file_storage.read(1024)
    valid_pdf_header = magic_header.startswith(b"%PDF-")
    valid_image_header = (
        (ext in {".jpg", ".jpeg"} and magic_header.startswith(b"\xff\xd8\xff"))
        or (ext == ".png" and magic_header.startswith(b"\x89PNG\r\n\x1a\n"))
    )
    if (is_pdf and not valid_pdf_header) or (is_image and not valid_image_header):
        raise InvalidPdfSignature(
            message=f"File '{raw_filename}' does not match its declared file type.",
            details=[{"field": "file", "issue": "File signature does not match its extension."}],
        )
    file_storage.seek(0)

    with open(stored_path, "wb") as f_out:
        while True:
            chunk = file_storage.read(65536)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                if os.path.exists(stored_path):
                    try:
                        os.remove(stored_path)
                    except OSError:
                        pass
                raise FileTooLarge(
                    message=f"File '{raw_filename}' exceeds the maximum allowed size of {max_mb} MB.",
                    details=[{"field": "file", "issue": f"Exceeded {max_mb} MB limit."}],
                )
            hasher.update(chunk)
            f_out.write(chunk)

    file_hash = hasher.hexdigest()

    doc = None
    decrypted_path = f"{stored_path}.decrypted"
    try:
        if is_pdf:
            doc = fitz.open(stored_path)
            is_encrypted = doc.is_encrypted
            if is_encrypted:
                if password is None:
                    raise PdfPasswordProtected(
                        message=f"File '{raw_filename}' requires a password.",
                        details=[{"field": "file", "issue": "Enter the PDF password to continue."}],
                    )
                if not doc.authenticate(password):
                    raise PdfInvalidPassword(
                        message=f"The password entered for '{raw_filename}' is incorrect.",
                        details=[{"field": "password", "issue": "The PDF password is incorrect."}],
                    )
            page_count = len(doc)
            if page_count == 0:
                raise PdfCorrupted(
                    message=f"File '{raw_filename}' contains no readable pages.",
                    details=[{"field": "file", "issue": "Zero pages in PDF document."}],
                )
            if page_count > max_pages:
                raise InvalidFileType(
                    message=f"PDF has {page_count} pages; the configured limit is {max_pages}.",
                    details=[{"field": "file", "issue": "Document page limit exceeded."}],
                )
            if is_encrypted:
                doc.save(
                    decrypted_path,
                    encryption=fitz.PDF_ENCRYPT_NONE,
                    garbage=3,
                    deflate=True,
                )
        else:
            with Image.open(stored_path) as image:
                if image.width * image.height > 100_000_000:
                    raise PdfCorrupted(
                        message=f"Image '{raw_filename}' exceeds the supported pixel count.",
                        details=[{"field": "file", "issue": "Image dimensions are too large."}],
                    )
                image.verify()
            image_doc = fitz.open(stored_path)
            pdf_bytes = image_doc.convert_to_pdf()
            image_doc.close()
            os.remove(stored_path)
            stored_path = os.path.join(upload_dir, f"{stmt_id}.pdf")
            with open(stored_path, "wb") as converted:
                converted.write(pdf_bytes)
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_count = 1
        doc.close()
        doc = None
        if is_pdf and os.path.exists(decrypted_path):
            os.replace(decrypted_path, stored_path)
    except AppError:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass
            doc = None
        if os.path.exists(stored_path):
            try:
                os.remove(stored_path)
            except OSError:
                pass
        if os.path.exists(decrypted_path):
            try:
                os.remove(decrypted_path)
            except OSError:
                pass
        raise
    except Exception as exc:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass
            doc = None
        if os.path.exists(stored_path):
            try:
                os.remove(stored_path)
            except OSError:
                pass
        if os.path.exists(decrypted_path):
            try:
                os.remove(decrypted_path)
            except OSError:
                pass
        raise PdfCorrupted(
            message=f"File '{raw_filename}' is corrupted and cannot be opened.",
            details=[{"field": "file", "issue": "The file signature or page content is invalid."}],
        )

    detected_pdf_type = PdfType.UNKNOWN.value

    statement = Statement(
        id=stmt_id,
        original_filename=clean_display_name,
        file_hash=file_hash,
        file_size_bytes=total_bytes,
        file_path=stored_path,
        page_count=page_count,
        pdf_type=detected_pdf_type,
        processing_status=ProcessingStatus.UPLOADED.value,
        pages_total=page_count,
        pages_done=0,
        progress_percent=0,
    )
    db.session.add(statement)
    db.session.commit()

    return statement, None
