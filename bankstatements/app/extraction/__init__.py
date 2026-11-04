"""Extraction package for bank statements."""

from app.extraction.pdf_detector import detect_document_pdf_type, detect_page_type
from app.extraction.text_extractor import extract_page_text, extract_page_words_with_coords, extract_tables_pdfplumber
from app.extraction.ocr_extractor import extract_page_words_ocr, is_tesseract_available
from app.extraction.table_extractor import cluster_words_into_rows, rows_to_text_lines
from app.extraction.bank_detector import detect_bank
from app.extraction.transaction_normalizer import normalize_transactions, parse_date, parse_money

__all__ = [
    "detect_document_pdf_type",
    "detect_page_type",
    "extract_page_text",
    "extract_page_words_with_coords",
    "extract_tables_pdfplumber",
    "extract_page_words_ocr",
    "is_tesseract_available",
    "cluster_words_into_rows",
    "rows_to_text_lines",
    "detect_bank",
    "normalize_transactions",
    "parse_date",
    "parse_money",
]
