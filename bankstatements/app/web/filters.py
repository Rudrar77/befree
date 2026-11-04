"""Jinja2 custom filters conforming to Section 3 requirements."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional
from markupsafe import Markup


def format_inr(val: Any) -> str:
    """Format decimal string to Indian grouped currency (e.g. ₹12,34,567.89).

    Uses pure string manipulation: NEVER float()!
    Handles:
        - null / None / empty -> '—'
        - negatives: '-12345.67' -> '-₹12,345.67'
        - integers: '500' -> '₹500.00'
        - large values: '10000000.00' -> '₹1,00,00,000.00'
    """
    if val is None:
        return "—"

    s = str(val).strip()
    if not s or s in ("null", "None", "—", "-"):
        return "—"

    is_negative = False
    if s.startswith("-"):
        is_negative = True
        s = s[1:].strip()

    # Split integer and decimal parts
    if "." in s:
        parts = s.split(".", 1)
        int_part = parts[0]
        dec_part = parts[1][:2].ljust(2, "0")
    else:
        int_part = s
        dec_part = "00"

    # Strip any existing commas
    int_part = int_part.replace(",", "")
    if not int_part:
        int_part = "0"

    # Indian numbering grouping:
    # Last 3 digits grouped together, then groups of 2 digits
    if len(int_part) <= 3:
        formatted_int = int_part
    else:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        # Group rest in pairs of 2 from right to left
        pairs = []
        while len(rest) > 2:
            pairs.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            pairs.append(rest)
        pairs.reverse()
        formatted_int = ",".join(pairs) + "," + last3

    result = f"₹{formatted_int}.{dec_part}"
    if is_negative:
        return f"-{result}"
    return result


def iso_to_display(val: Any) -> str:
    """Format ISO date or datetime string to 'DD MMM YYYY'. Null -> '—'."""
    if not val:
        return "—"

    if isinstance(val, (datetime, date)):
        return val.strftime("%d %b %Y")

    s = str(val).strip()
    if not s or s in ("null", "None"):
        return "—"

    # Take the date component 'YYYY-MM-DD'
    date_str = s[:10]
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%d %b %Y")
    except ValueError:
        return s


def status_badge(status_str: Any) -> Markup:
    """Render a Bootstrap 5 badge for a status string with semantic color and text."""
    if not status_str:
        return Markup('<span class="badge bg-secondary">—</span>')

    s = str(status_str).lower().strip()
    color = "secondary"

    if s in ("completed", "valid", "matched"):
        color = "success"
    elif s in ("completed_with_warnings", "warning", "possible_duplicate"):
        color = "warning text-dark"
    elif s in ("failed", "error", "mismatch", "exact_duplicate"):
        color = "danger"
    elif s in ("processing", "extracting", "classifying", "ocr"):
        color = "primary"
    elif s in ("queued", "uploaded"):
        color = "info text-dark"

    display_text = s.replace("_", " ").title()
    html = f'<span class="badge bg-{color}">{display_text}</span>'
    return Markup(html)

