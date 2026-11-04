"""Table extraction and word clustering into structured rows and columns."""

from __future__ import annotations

from typing import Any, List, Optional


def cluster_words_into_rows(
    words: List[dict[str, Any]],
    y_tolerance: float = 5.0,
) -> List[List[dict[str, Any]]]:
    """Cluster bounding-box words into horizontal rows based on vertical proximity.

    Args:
        words: List of word dicts with 'text', 'x0', 'y0', 'x1', 'y1'
        y_tolerance: Vertical distance within which words belong to the same row

    Returns:
        List of rows, where each row is a list of words sorted horizontally (by x0).
    """
    if not words:
        return []

    # Sort words primarily by y0, secondarily by x0
    sorted_words = sorted(words, key=lambda w: (w["y0"], w["x0"]))

    rows: List[List[dict[str, Any]]] = []
    current_row: List[dict[str, Any]] = [sorted_words[0]]
    current_y = sorted_words[0]["y0"]

    for w in sorted_words[1:]:
        if abs(w["y0"] - current_y) <= y_tolerance:
            current_row.append(w)
        else:
            # Sort current row by x0 before saving
            current_row.sort(key=lambda item: item["x0"])
            rows.append(current_row)
            current_row = [w]
            current_y = w["y0"]

    if current_row:
        current_row.sort(key=lambda item: item["x0"])
        rows.append(current_row)

    return rows


def rows_to_text_lines(rows: List[List[dict[str, Any]]]) -> List[str]:
    """Convert clustered word rows into formatted text lines."""
    lines: List[str] = []
    for row in rows:
        line_text = " ".join(w["text"] for w in row).strip()
        if line_text:
            lines.append(line_text)
    return lines


def identify_columns_from_headers(
    header_row: List[dict[str, Any]],
) -> List[dict[str, Any]]:
    """Determine column boundaries (x_start, x_end, name) from a detected header row.

    Args:
        header_row: List of words belonging to the table header line

    Returns:
        List of column specs: [{'name': str, 'x0': float, 'x1': float}]
    """
    columns: List[dict[str, Any]] = []
    for w in header_row:
        columns.append({
            "name": w["text"].lower(),
            "x0": w["x0"],
            "x1": w["x1"],
        })
    return columns


def assign_words_to_columns(
    row_words: List[dict[str, Any]],
    columns: List[dict[str, Any]],
) -> dict[str, str]:
    """Assign words in a row to the nearest column by horizontal overlap or distance.

    Args:
        row_words: List of words in a row
        columns: List of column definitions with 'name', 'x0', 'x1'

    Returns:
        Dictionary mapping column name to text string
    """
    col_text: dict[str, List[str]] = {col["name"]: [] for col in columns}

    for w in row_words:
        w_mid = (w["x0"] + w["x1"]) / 2.0
        # Find closest column
        best_col = None
        best_dist = float("inf")
        for col in columns:
            col_mid = (col["x0"] + col["x1"]) / 2.0
            dist = abs(w_mid - col_mid)
            if dist < best_dist:
                best_dist = dist
                best_col = col["name"]

        if best_col:
            col_text[best_col].append(w["text"])

    return {k: " ".join(v).strip() for k, v in col_text.items()}
