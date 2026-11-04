"""PDF type detection (text vs scanned vs mixed)."""

from __future__ import annotations

from typing import Any, List, Tuple
import pymupdf as fitz  # PyMuPDF


def _image_coverage_ratio(page: fitz.Page) -> float:
    """Return the union area of visible raster images as a fraction of page area."""
    page_area = page.rect.get_area()
    if page_area <= 0:
        return 0.0

    image_rects: list[fitz.Rect] = []
    for image in page.get_images(full=True):
        image_rects.extend(
            clipped
            for rect in page.get_image_rects(image[0])
            if (clipped := rect & page.rect).get_area() > 0
        )
    if not image_rects:
        return 0.0

    y_edges = sorted({coord for rect in image_rects for coord in (rect.y0, rect.y1)})
    covered_area = 0.0
    for y0, y1 in zip(y_edges, y_edges[1:]):
        intervals = sorted(
            (rect.x0, rect.x1)
            for rect in image_rects
            if rect.y0 < y1 and rect.y1 > y0
        )
        if not intervals:
            continue
        span_start, span_end = intervals[0]
        covered_width = 0.0
        for start, end in intervals[1:]:
            if start <= span_end:
                span_end = max(span_end, end)
            else:
                covered_width += span_end - span_start
                span_start, span_end = start, end
        covered_width += span_end - span_start
        covered_area += covered_width * (y1 - y0)
    return min(covered_area / page_area, 1.0)


def detect_page_type(
    page: fitz.Page,
    min_chars: int = 50,
    image_coverage_threshold: float = 0.2,
) -> Tuple[str, int]:
    """Classify a page by native text and visible raster coverage.

    Returns:
        tuple of (method: 'text' | 'ocr' | 'mixed', char_count: int)
    """
    text = page.get_text("text").strip()
    char_count = len(text)
    has_readable_text = char_count >= min_chars
    has_substantial_image = _image_coverage_ratio(page) >= image_coverage_threshold
    if has_readable_text and has_substantial_image:
        return "mixed", char_count
    if has_readable_text:
        return "text", char_count
    return "ocr", char_count


def detect_document_pdf_type(
    doc: fitz.Document,
    min_chars: int = 50,
    image_coverage_threshold: float = 0.2,
) -> Tuple[str, List[dict[str, Any]]]:
    """Inspect all pages of a PDF document and determine overall document type.

    Returns:
        tuple of (pdf_type: 'text' | 'scanned' | 'mixed', page_methods: list[dict])
    """
    page_methods: List[dict[str, Any]] = []
    text_pages = 0
    scanned_pages = 0

    for i in range(len(doc)):
        page = doc[i]
        image_coverage = _image_coverage_ratio(page)
        method, char_count = detect_page_type(
            page,
            min_chars=min_chars,
            image_coverage_threshold=image_coverage_threshold,
        )
        is_ocr = method in {"ocr", "mixed"}
        if method in {"ocr", "mixed"}:
            scanned_pages += 1
        if method in {"text", "mixed"}:
            text_pages += 1

        page_methods.append({
            "page": i + 1,
            "method": method,
            "ocr_used": is_ocr,
            "char_count": char_count,
            "image_coverage": round(image_coverage, 4),
            "error": None,
        })

    if text_pages > 0 and scanned_pages == 0:
        overall_type = "text"
    elif scanned_pages > 0 and text_pages == 0:
        overall_type = "scanned"
    elif text_pages > 0 and scanned_pages > 0:
        overall_type = "mixed"
    else:
        overall_type = "unknown"

    return overall_type, page_methods
