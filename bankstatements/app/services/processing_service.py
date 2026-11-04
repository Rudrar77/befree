"""Background statement processing service."""

from __future__ import annotations

import logging
import os
import traceback
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, List, Optional
import pymupdf as fitz
from flask import current_app
from PIL import Image

from app.classification.confidence import classify_transactions_pipeline
from app.errors import ConflictError, NotFoundError
from app.extensions import db, executor
from app.extraction.bank_detector import detect_bank, detect_bank_name
from app.extraction.document_ocr import (
    OCRProviderError,
    extract_with_fallback,
    verify_ocr_result,
)
from app.extraction.pdf_detector import detect_document_pdf_type, detect_page_type
from app.extraction.table_extractor import cluster_words_into_rows, rows_to_text_lines
from app.extraction.text_extractor import (
    extract_page_text,
    extract_page_words_with_coords,
    extract_tables_pdfplumber,
)
from app.extraction.transaction_normalizer import normalize_transactions
from app.models.category import Category
from app.models.classification_rule import ClassificationRule
from app.models.processing_log import ProcessingLog
from app.models.statement import PdfType, ProcessingStatus, Statement
from app.models.transaction import Transaction
from app.models.unresolved_row import UnresolvedRow
from app.models.validation_result import ValidationResult
from app.services.pretrained_classifier import get_pretrained_classifier
from app.validation.anomaly_detector import detect_anomalies
from app.validation.balance_reconciliation import reconcile_statement_balances
from app.validation.data_validator import validate_statement_data
from app.validation.duplicate_detector import detect_duplicates

logger = logging.getLogger(__name__)


def trigger_statement_processing(statement_id: str) -> Statement:
    """Validate statement state and enqueue background processing.

    Returns:
        Statement instance in 'queued' or 'processing' status.
    Raises:
        ConflictError (409) if statement is already 'processing'.
    """
    stmt = db.session.get(Statement, statement_id)
    if not stmt:
        raise NotFoundError(message=f"Statement with ID '{statement_id}' not found.")

    if stmt.processing_status == ProcessingStatus.PROCESSING.value:
        raise ConflictError(message=f"Statement '{statement_id}' is already being processed.")

    stmt.processing_status = ProcessingStatus.QUEUED.value
    stmt.current_step = "queued"
    stmt.progress_percent = 5
    stmt.error_message = None
    stmt.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    # Pass real Flask app instance to worker
    real_app = current_app._get_current_object()
    executor.submit(run_processing_pipeline, real_app, statement_id)

    return stmt


def run_processing_pipeline(app: Any, statement_id: str) -> None:
    """Worker function executed inside ThreadPoolExecutor.

    Guarantees:
        - Own app_context
        - db.session.remove() in finally
        - Atomic commit: clears previous rows and inserts new rows in one transaction
        - On exception: rolls back, keeps prior results or records failure safely
    """
    with app.app_context():
        try:
            stmt = db.session.get(Statement, statement_id)
            if not stmt:
                return

            stmt.processing_status = ProcessingStatus.PROCESSING.value
            stmt.current_step = "ocr"
            stmt.progress_percent = 10
            stmt.updated_at = datetime.now(timezone.utc)
            db.session.commit()

            file_path = stmt.file_path
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Stored statement file not found on disk: {file_path}")

            # -------------------------------------------------------------
            # Step 1: PDF inspection & Page-by-page extraction
            # -------------------------------------------------------------
            doc = fitz.open(file_path)
            total_pages = len(doc)
            stmt.pages_total = total_pages
            stmt.page_count = total_pages

            min_chars = app.config.get("TEXT_MIN_CHARS_PER_PAGE", 50)
            ocr_dpi = app.config.get("OCR_DPI", 300)
            image_coverage_threshold = app.config.get(
                "OCR_IMAGE_COVERAGE_THRESHOLD", 0.20
            )

            overall_pdf_type, page_methods = detect_document_pdf_type(
                doc,
                min_chars=min_chars,
                image_coverage_threshold=image_coverage_threshold,
            )
            stmt.pdf_type = overall_pdf_type

            pages_content: List[dict[str, Any]] = []
            sample_header_text = ""
            fallback_notice_recorded = False

            for p_idx in range(total_pages):
                page = doc[p_idx]
                p_num = p_idx + 1
                stmt.current_step = f"ocr_page_{p_num}"
                stmt.progress_percent = int(10 + (p_idx / max(total_pages, 1)) * 30)
                stmt.updated_at = datetime.now(timezone.utc)
                db.session.commit()
                logger.info(
                    "Extracting statement %s page %s/%s",
                    statement_id,
                    p_num,
                    total_pages,
                )
                method, _ = detect_page_type(
                    page,
                    min_chars=min_chars,
                    image_coverage_threshold=image_coverage_threshold,
                )

                page_text = ""
                native_text = extract_page_text(doc, p_idx)
                tables: List[List[List[Optional[str]]]] = []
                word_rows: List[str] = []
                clustered = []
                ocr_warnings: List[str] = []

                if method in {"text", "mixed"}:
                    page_text = native_text
                    # Attempt pdfplumber tables
                    tables = extract_tables_pdfplumber(file_path, p_idx)
                    words = extract_page_words_with_coords(doc, p_idx)
                    if method == "mixed":
                        pix = page.get_pixmap(dpi=ocr_dpi)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        try:
                            ocr_result = extract_with_fallback(
                                img,
                                app.config.get("OCR_PROVIDER", "paddleocr"),
                                app.config.get("OCR_FALLBACK_PROVIDER", "tesseract"),
                                use_gpu=app.config.get("OCR_USE_GPU", False),
                            )
                            try:
                                ocr_warnings.extend(verify_ocr_result(
                                    img,
                                    ocr_result,
                                    app.config.get("OCR_SECONDARY_PROVIDER"),
                                    use_gpu=app.config.get("OCR_USE_GPU", False),
                                ))
                            except OCRProviderError as exc:
                                logger.warning("Secondary OCR verification unavailable: %s", exc)
                                ocr_warnings.append("Secondary OCR verification could not complete.")
                            scale = 72.0 / ocr_dpi
                            ocr_words = ocr_result["words"]
                            for word in ocr_words:
                                for key in ("x0", "x1", "y0", "y1"):
                                    word[key] = float(word[key]) * scale
                            existing = {
                                (word["text"].lower(), round(word["x0"]), round(word["y0"]))
                                for word in words
                            }
                            words.extend(
                                word for word in ocr_words
                                if (word["text"].lower(), round(word["x0"]), round(word["y0"]))
                                not in existing
                            )
                            tables.extend(ocr_result.get("tables") or [])
                            for warning in ocr_result.get("warnings") or []:
                                if warning.startswith("Primary OCR provider"):
                                    if fallback_notice_recorded:
                                        continue
                                    fallback_notice_recorded = True
                                ocr_warnings.append(warning)
                            if ocr_result.get("text"):
                                page_text = f"{page_text}\n{ocr_result['text']}".strip()
                            page_methods[p_idx]["ocr_used"] = True
                            page_methods[p_idx]["provider"] = ocr_result.get("provider")
                        except OCRProviderError as exc:
                            page_methods[p_idx]["error"] = str(exc)
                            ocr_warnings.append("Image content on this page was not OCR-processed.")
                    clustered = cluster_words_into_rows(words)
                    word_rows = rows_to_text_lines(clustered)
                else:
                    # Scanned page: render image and run OCR
                    pix = page.get_pixmap(dpi=ocr_dpi)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    try:
                        ocr_result = extract_with_fallback(
                            img,
                            app.config.get("OCR_PROVIDER", "paddleocr"),
                            app.config.get("OCR_FALLBACK_PROVIDER", "tesseract"),
                            use_gpu=app.config.get("OCR_USE_GPU", False),
                        )
                        try:
                            ocr_warnings.extend(verify_ocr_result(
                                img,
                                ocr_result,
                                app.config.get("OCR_SECONDARY_PROVIDER"),
                                use_gpu=app.config.get("OCR_USE_GPU", False),
                            ))
                        except OCRProviderError as exc:
                            logger.warning("Secondary OCR verification unavailable: %s", exc)
                            ocr_warnings.append("Secondary OCR verification could not complete.")
                        words = ocr_result["words"]
                        if native_text.strip():
                            native_words = extract_page_words_with_coords(doc, p_idx)
                            existing = {
                                (word["text"].lower(), round(word["x0"]), round(word["y0"]))
                                for word in native_words
                            }
                            ocr_scale = 72.0 / ocr_dpi
                            for word in words:
                                for key in ("x0", "x1", "y0", "y1"):
                                    word[key] = float(word[key]) * ocr_scale
                            words = native_words + [
                                word for word in words
                                if (word["text"].lower(), round(word["x0"]), round(word["y0"]))
                                not in existing
                            ]
                        tables = ocr_result.get("tables") or []
                        for warning in ocr_result.get("warnings") or []:
                            if warning.startswith("Primary OCR provider"):
                                if fallback_notice_recorded:
                                    continue
                                fallback_notice_recorded = True
                            ocr_warnings.append(warning)
                        clustered = cluster_words_into_rows(words)
                        word_rows = rows_to_text_lines(clustered)
                        page_text = "\n".join(
                            text for text in (native_text, ocr_result.get("text")) if text
                        ) or "\n".join(word_rows)
                        page_methods[p_idx]["provider"] = ocr_result.get("provider")
                    except OCRProviderError as exc:
                        page_methods[p_idx]["error"] = str(exc)
                        words = []

                if page_methods[p_idx].get("error"):
                    page_methods[p_idx]["review_required"] = True
                if ocr_warnings:
                    page_methods[p_idx]["warnings"] = ocr_warnings
                    page_methods[p_idx]["review_required"] = True

                if p_idx == 0:
                    sample_header_text = page_text

                pages_content.append({
                    "page_num": p_num,
                    "method": method,
                    "text": page_text,
                    "tables": tables,
                    "lines": word_rows,
                    "word_rows": clustered,
                    "ocr_warnings": ocr_warnings,
                })

                stmt.pages_done = p_num
                stmt.progress_percent = int(10 + (p_num / total_pages) * 30)
                stmt.updated_at = datetime.now(timezone.utc)
                db.session.commit()

            page_method_names = {page.get("method") for page in page_methods}
            if "mixed" in page_method_names or {"text", "ocr"}.issubset(page_method_names):
                stmt.pdf_type = PdfType.MIXED.value
            elif "text" in page_method_names:
                stmt.pdf_type = PdfType.TEXT.value
            elif "ocr" in page_method_names:
                stmt.pdf_type = PdfType.SCANNED.value

            doc.close()
            stmt.page_methods = page_methods

            # -------------------------------------------------------------
            # Step 2: Bank Detection & Parsing
            # -------------------------------------------------------------
            stmt.current_step = "extraction"
            stmt.progress_percent = 45
            stmt.updated_at = datetime.now(timezone.utc)
            db.session.commit()

            full_text = "\n".join(p.get("text") or "" for p in pages_content)
            detect_source = full_text.strip() or sample_header_text
            parser, _ = detect_bank(detect_source)
            stmt.bank_name = detect_bank_name(detect_source) or parser.bank_name

            account_info = parser.parse_account_info(detect_source)
            stmt.account_holder_name = account_info.get("account_holder_name")
            stmt.account_number_masked = account_info.get("account_number_masked")
            stmt.ifsc = account_info.get("ifsc")
            stmt.branch_name = account_info.get("branch_name")
            stmt.period_start = account_info.get("period_start")
            stmt.period_end = account_info.get("period_end")
            stmt.opening_balance = account_info.get("opening_balance")
            stmt.closing_balance = account_info.get("closing_balance")

            raw_txns, raw_unresolved = parser.parse_transactions(pages_content)

            # -------------------------------------------------------------
            # Step 3: Transaction Normalization
            # -------------------------------------------------------------
            stmt.current_step = "normalization"
            stmt.progress_percent = 60
            stmt.updated_at = datetime.now(timezone.utc)
            db.session.commit()

            norm_txns, more_unresolved = normalize_transactions(
                raw_txns, statement_id=statement_id, opening_balance=stmt.opening_balance
            )
            all_unresolved = raw_unresolved + more_unresolved

            # -------------------------------------------------------------
            # Step 4: Classification
            # -------------------------------------------------------------
            stmt.current_step = "classification"
            stmt.progress_percent = 75
            stmt.updated_at = datetime.now(timezone.utc)
            db.session.commit()

            rules = db.session.query(ClassificationRule).join(Category).all()
            all_cats = db.session.query(Category).all()
            cat_map = {c.name: c for c in all_cats}

            ml_model = get_pretrained_classifier()
            conf_threshold = app.config.get("CONFIDENCE_THRESHOLD", 0.70)
            ml_conf_threshold = app.config.get(
                "PRETRAINED_TRANSACTION_CONFIDENCE_THRESHOLD", 0.30
            )

            extraction_review_flags = {
                txn["id"]: bool(txn.get("needs_review"))
                for txn in norm_txns
            }
            classify_transactions_pipeline(
                norm_txns,
                rules=rules,
                category_map_by_name=cat_map,
                ml_classifier=ml_model,
                confidence_threshold=conf_threshold,
                ml_confidence_threshold=ml_conf_threshold,
            )
            for txn in norm_txns:
                txn["needs_review"] = bool(
                    txn.get("needs_review") or extraction_review_flags.get(txn["id"])
                )

            # -------------------------------------------------------------
            # Step 5: Validation, Duplicates, Reconciliation, Anomalies
            # -------------------------------------------------------------
            stmt.current_step = "validation"
            stmt.progress_percent = 90
            stmt.updated_at = datetime.now(timezone.utc)
            db.session.commit()

            # Duplicates
            detect_duplicates(norm_txns)

            # Anomalies
            detect_anomalies(norm_txns)

            # Statement Validation
            val_issues = validate_statement_data(
                statement_info=stmt.to_dict(),
                transactions=norm_txns,
                unresolved_rows=all_unresolved,
            )

            # Reconciliation
            recon_tol = Decimal(str(app.config.get("RECONCILIATION_TOLERANCE", 0.01)))
            recon_res = reconcile_statement_balances(
                opening_balance=stmt.opening_balance,
                closing_balance=stmt.closing_balance,
                transactions=norm_txns,
                tolerance=recon_tol,
            )

            is_mismatch = recon_res["status"] == "mismatch"
            has_val_errors = any(i["severity"] == "error" for i in val_issues)
            has_unresolved = len(all_unresolved) > 0
            has_review_txns = any(t.get("needs_review") for t in norm_txns)
            has_extraction_errors = any(
                pm.get("error") or pm.get("review_required")
                for pm in page_methods
            )

            stmt.needs_review = (
                is_mismatch
                or has_val_errors
                or has_unresolved
                or has_review_txns
                or has_extraction_errors
            )

            if has_unresolved or has_val_errors or is_mismatch or has_extraction_errors:
                stmt.processing_status = ProcessingStatus.COMPLETED_WITH_WARNINGS.value
            else:
                stmt.processing_status = ProcessingStatus.COMPLETED.value

            stmt.transaction_count = len(norm_txns)
            stmt.unresolved_count = len(all_unresolved)

            # -------------------------------------------------------------
            # Step 6: Atomic DB persistence
            # -------------------------------------------------------------
            # Clear previous results for reprocessing
            db.session.query(Transaction).filter_by(statement_id=statement_id).delete()
            db.session.query(UnresolvedRow).filter_by(statement_id=statement_id).delete()
            db.session.query(ValidationResult).filter_by(statement_id=statement_id).delete()

            # Insert normalized transactions
            for t_dict in norm_txns:
                txn_obj = Transaction(
                    id=t_dict["id"],
                    statement_id=statement_id,
                    transaction_date=t_dict.get("transaction_date"),
                    description=t_dict.get("description", ""),
                    original_description=t_dict.get("original_description", ""),
                    debit=t_dict.get("debit"),
                    credit=t_dict.get("credit"),
                    balance=t_dict.get("balance"),
                    reference_number=t_dict.get("reference_number"),
                    transaction_id=t_dict.get("transaction_id"),
                    mode=t_dict.get("mode"),
                    currency=t_dict.get("currency"),
                    original_amount_text=t_dict.get("original_amount_text"),
                    source_row=t_dict.get("source_row"),
                    extraction_confidence=t_dict.get("extraction_confidence"),
                    category_id=t_dict.get("category_id"),
                    classification_method=t_dict.get("classification_method", "none"),
                    confidence=t_dict.get("confidence"),
                    applied_rule_id=t_dict.get("applied_rule_id"),
                    model_version=t_dict.get("model_version"),
                    manual_override=t_dict.get("manual_override", False),
                    needs_review=t_dict.get("needs_review", False),
                    duplicate_status=t_dict.get("duplicate_status", "none"),
                    duplicate_of=t_dict.get("duplicate_of"),
                    validation_status=t_dict.get("validation_status", "valid"),
                    anomaly_flags=t_dict.get("anomaly_flags", []),
                    source_page=t_dict.get("source_page"),
                    extraction_method=t_dict.get("extraction_method", "text"),
                    warnings=t_dict.get("warnings", []),
                    notes=t_dict.get("notes"),
                )
                db.session.add(txn_obj)

            # Insert unresolved rows
            for u_dict in all_unresolved:
                u_obj = UnresolvedRow(
                    id=u_dict.get("id"),
                    statement_id=statement_id,
                    source_page=u_dict.get("source_page"),
                    raw_text=u_dict.get("raw_text", ""),
                    reason=u_dict.get("reason", "Unparsed row"),
                    extraction_method=u_dict.get("extraction_method", "text"),
                )
                db.session.add(u_obj)

            # Insert validation issues
            for v_dict in val_issues:
                v_obj = ValidationResult(
                    id=v_dict["id"],
                    statement_id=statement_id,
                    severity=v_dict["severity"],
                    code=v_dict["code"],
                    message=v_dict["message"],
                    transaction_id=v_dict.get("transaction_id"),
                    transaction_description=v_dict.get("transaction_description"),
                )
                db.session.add(v_obj)

            # Finalize statement status
            stmt.current_step = "done"
            stmt.progress_percent = 100
            stmt.updated_at = datetime.now(timezone.utc)

            # Add processing log
            p_log = ProcessingLog(
                statement_id=statement_id,
                step="done",
                status="success",
                message=f"Processed {len(norm_txns)} transactions, {len(all_unresolved)} unresolved rows.",
            )
            db.session.add(p_log)
            db.session.commit()

        except Exception as exc:
            db.session.rollback()
            logger.exception("Processing failed for statement %s: %s", statement_id, exc)
            try:
                fail_stmt = db.session.get(Statement, statement_id)
                if fail_stmt:
                    fail_stmt.processing_status = ProcessingStatus.FAILED.value
                    fail_stmt.error_message = "Statement processing encountered an internal error. Please check file formatting or retry."
                    fail_stmt.updated_at = datetime.now(timezone.utc)
                    log_entry = ProcessingLog(
                        statement_id=statement_id,
                        step=fail_stmt.current_step or "unknown",
                        status="failed",
                        message=str(exc)[:500],
                    )
                    db.session.add(log_entry)
                    db.session.commit()
            except Exception:
                db.session.rollback()
        finally:
            db.session.remove()
