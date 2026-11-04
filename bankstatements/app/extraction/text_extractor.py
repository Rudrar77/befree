"""Text extraction from digital PDFs using PyMuPDF and pdfplumber."""

from __future__ import annotations

from typing import Any, List, Optional
import pymupdf as fitz
import pdfplumber


def extract_page_text(doc: fitz.Document, page_num: int) -> str:
    """Extract plain text of a page using PyMuPDF (0-indexed)."""
    if page_num < 0 or page_num >= len(doc):
        return ""
    return doc[page_num].get_text("text")


def extract_page_words_with_coords(doc: fitz.Document, page_num: int) -> List[dict[str, Any]]:
    """Extract words with bounding box coordinates from a page using PyMuPDF.

    Returns:
        List of dicts: {"text": str, "x0": float, "y0": float, "x1": float, "y1": float}
    """
    page = doc[page_num]
    # get_text("words") returns tuples: (x0, y0, x1, y1, "word", block_no, line_no, word_no)
    words = page.get_text("words")
    result: List[dict[str, Any]] = []
    for w in words:
        result.append({
            "text": str(w[4]),
            "x0": float(w[0]),
            "y0": float(w[1]),
            "x1": float(w[2]),
            "y1": float(w[3]),
            "block_no": int(w[5]),
            "line_no": int(w[6]),
        })
    return result


def extract_tables_pdfplumber(pdf_path: str, page_num: int) -> List[List[List[Optional[str]]]]:
    """Extract tables from a single page using pdfplumber (0-indexed).

    Returns:
        List of tables, where each table is a list of rows, and each row is a list of cell strings.
    """
    tables: List[List[List[Optional[str]]]] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_num < len(pdf.pages):
                page = pdf.pages[page_num]
                extracted = page.extract_tables()
                if extracted:
                    tables.extend(extracted)
    except Exception:
        pass
    return tables

