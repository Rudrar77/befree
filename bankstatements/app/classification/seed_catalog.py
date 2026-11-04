"""Load bundled classification rules from the seed catalog CSV."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "classification_rules.csv"

VALID_MATCH_TYPES = {"exact", "partial", "regex"}
VALID_DIRECTIONS = {"any", "debit", "credit"}


def load_seed_rules(path: Path | None = None) -> List[dict[str, Any]]:
    """Parse keyword,category,match_type,priority,direction rows.

    Extra commas in regex keywords are handled by splitting from the right.
    Duplicate (keyword, category) pairs keep the highest-priority row.
    """
    catalog = path or CATALOG_PATH
    if not catalog.exists():
        return []

    best: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_line in catalog.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("keyword,"):
            continue
        parts = [p.strip() for p in line.rsplit(",", 4)]
        if len(parts) != 5:
            continue
        keyword, category, match_type, priority_s, direction = parts
        match_type = match_type.lower()
        direction_norm = direction.lower().replace(" add in rules", "").strip()
        if direction_norm.startswith("credit"):
            direction_norm = "credit"
        elif direction_norm.startswith("debit"):
            direction_norm = "debit"
        elif direction_norm != "any":
            direction_norm = "any"
        if match_type not in VALID_MATCH_TYPES:
            continue
        try:
            priority = int(priority_s)
        except ValueError:
            continue
        if not keyword or not category:
            continue
        row = {
            "keyword": keyword,
            "category": category,
            "match_type": match_type,
            "priority": priority,
            "direction": direction_norm,
        }
        key = (keyword.lower(), category.lower())
        existing = best.get(key)
        if existing is None or priority > existing["priority"]:
            best[key] = row
    return list(best.values())
