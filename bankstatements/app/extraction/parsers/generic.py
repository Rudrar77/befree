"""Shared bank statement parser using flexible regexes and table heuristics."""

from __future__ import annotations

import re
from typing import Any, List, Optional
from app.extraction.bank_parser import BankParser
from app.extraction.transaction_normalizer import parse_date, parse_money


class GenericParser(BankParser):
    """Parser used for statements from any bank."""

    @property
    def bank_name(self) -> str:
        return "Generic"

    @property
    def ifsc_prefix(self) -> Optional[str]:
        return None

    def detect(self, text: str) -> float:
        # Generic parser always matches as a fallback with low baseline score
        return 0.1

    def parse_account_info(self, text: str) -> dict[str, Any]:
        info: dict[str, Any] = {
            "account_holder_name": None,
            "account_number_masked": None,
            "ifsc": None,
            "branch_name": None,
            "period_start": None,
            "period_end": None,
            "opening_balance": None,
            "closing_balance": None,
        }

        # 1. Masked account number extraction
        acc_match = re.search(r"(?i)(?:account\s*(?:no|number)|a/c\s*(?:no|num)?)[.:\s]*([X*\d\s-]{6,25})", text)
        if acc_match:
            raw_acc = re.sub(r"[\s-]", "", acc_match.group(1))
            if len(raw_acc) >= 4:
                # Mask all except last 4 digits
                last4 = raw_acc[-4:]
                info["account_number_masked"] = f"XXXXXX{last4}"

        # 2. IFSC extraction
        ifsc_match = re.search(
            r"(?i)(?:RTGS/NEFT[ \t]*)?IFSC(?:[ \t]+CODE)?[ \t]*[:.]?[ \t]*([A-Z]{4}0[A-Z0-9]{6})\b",
            text,
        )
        if not ifsc_match:
            ifsc_label = re.search(r"\bIFSC(?:\s+CODE)?\b", text, re.IGNORECASE)
            if ifsc_label:
                ifsc_match = re.search(
                    r"\b([A-Z]{4}0[A-Z0-9]{6})\b",
                    text[ifsc_label.end():ifsc_label.end() + 500],
                    re.IGNORECASE,
                )
        if not ifsc_match:
            header = text[:3000].lower()
            bank_prefix_markers = (
                ("HDFC", ("hdfc bank",)),
                ("ICIC", ("icici bank",)),
                ("SBIN", ("state bank of india", "state bank")),
                ("UTIB", ("axis bank",)),
                ("BARB", ("bank of baroda",)),
                ("KKBK", ("kotak mahindra bank", "kotak bank")),
                ("UCBA", ("uco bank",)),
                ("UBIN", ("union bank of india", "union bank")),
            )
            for prefix, markers in bank_prefix_markers:
                if any(marker in header for marker in markers):
                    ifsc_match = re.search(
                        rf"\b({prefix}0[A-Z0-9]{{6}})\b", text, re.IGNORECASE
                    )
                    if ifsc_match:
                        break
        if not ifsc_match:
            ifsc_match = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", text)
        if ifsc_match:
            info["ifsc"] = ifsc_match.group(1).upper()

        # 3. Account holder name extraction
        name_match = re.search(
            r"(?i)(?:customer\s*name|account\s*holder|name\s*of\s*account\s*holder|name)[.:\s]+([A-Za-z\s.]{3,40})",
            text,
        )
        if name_match:
            cand = name_match.group(1).strip()
            if not any(kw in cand.lower() for kw in ("statement", "bank", "branch", "date", "number")):
                info["account_holder_name"] = cand

        # 4. Branch extraction
        branch_match = re.search(
            r"(?im)^\s*(?:account\s*)?branch(?:\s*name)?[.:\s]+([A-Za-z0-9 ,-]{3,50})",
            text,
        )
        if branch_match:
            info["branch_name"] = branch_match.group(1).strip()

        # 5. Period extraction (from ... to ...)
        date_pattern = (
            r"(?:[0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}"
            r"|[A-Za-z]{3,9}\s+[0-9]{1,2},?\s+[0-9]{4})"
        )
        period_match = re.search(
            rf"(?i)(?:period(?:\s+from)?|from)\s*[:]?\s*-?\s*({date_pattern})\s*(?:to\s*:?|-)\s*({date_pattern})",
            text,
        )
        if period_match:
            info["period_start"] = parse_date(period_match.group(1))
            info["period_end"] = parse_date(period_match.group(2))

        # 6. Opening & Closing balance
        opening_regex = (
            r"(?im)(?:opening\s*(?:balance)?|open\s*bal|balance\s*forward|brought\s*forward|b/f|bf)"
            r"[\s:./-]*([₹$€£]?\s?[0-9][0-9,]*(?:\.\d{2})?(?:\s*(?:cr|dr))?)"
        )
        close_regex = (
            r"(?im)(?:closing\s*(?:balance)?|close\s*bal|carried\s*forward|c/f|balance\s*as\s*on|balance\s*forward)"
            r"[\s:./-]*([₹$€£]?\s?[0-9][0-9,]*(?:\.\d{2})?(?:\s*(?:cr|dr))?)"
        )

        open_bal = re.search(opening_regex, text)
        if open_bal:
            info["opening_balance"] = parse_money(open_bal.group(1))

        close_bal = re.search(close_regex, text)
        if close_bal:
            info["closing_balance"] = parse_money(close_bal.group(1))

        summary_match = re.search(
            r"(?is)statement\s+summary\s*:?(.*?)(?:generated\s+on|$)",
            text,
        )
        if summary_match:
            summary_lines = [line.strip() for line in summary_match.group(1).splitlines()]
            has_opening_label = any(
                re.fullmatch(r"opening\s+balance", line, re.IGNORECASE)
                for line in summary_lines
            )
            has_closing_label = any(
                re.fullmatch(r"closing\s+bal(?:ance)?", line, re.IGNORECASE)
                for line in summary_lines
            )
            summary_values = [
                line for line in summary_lines
                if re.fullmatch(r"[0-9][0-9,]*(?:\.[0-9]{2})?", line)
            ]
            if has_opening_label and has_closing_label and len(summary_values) >= 6:
                info["opening_balance"] = parse_money(summary_values[0])
                info["closing_balance"] = parse_money(summary_values[5])

        return info

    def _is_usable_table(self, table: List[List[Optional[str]]]) -> bool:
        """Reject pdfplumber tables that collapsed many rows into one cell."""
        if not table or len(table) < 2:
            return False
        first_data = table[1]
        newline_cells = sum(1 for cell in first_data if cell and str(cell).count("\n") >= 3)
        return newline_cells < 2

    def _column_anchors(
        self, word_row: List[dict[str, Any]]
    ) -> Optional[dict[str, float]]:
        """Find transaction column centers from a statement's header row."""
        groups: dict[str, list[float]] = {
            "date": [],
            "description": [],
            "reference": [],
            "debit": [],
            "credit": [],
            "balance": [],
        }

        for word in word_row:
            token = word["text"].lower().strip(" .:")
            center = (float(word["x0"]) + float(word["x1"])) / 2
            if token == "date":
                groups["date"].append(center)
            elif any(key in token for key in ("narration", "description", "particular")):
                groups["description"].append(center)
            elif any(key in token for key in ("ref", "cheque", "chq")):
                groups["reference"].append(center)
            elif any(key in token for key in ("withdrawal", "debit")):
                groups["debit"].append(center)
            elif any(key in token for key in ("deposit", "credit")):
                groups["credit"].append(center)
            elif token in ("balance", "bal"):
                groups["balance"].append(center)

        if not groups["date"] or not groups["description"]:
            return None

        anchors = {
            key: sum(positions) / len(positions)
            for key, positions in groups.items()
            if positions
        }
        if not {"debit", "credit", "balance"}.issubset(anchors):
            return None
        return anchors

    def _parse_coordinate_rows(
        self,
        pages_content: List[dict[str, Any]],
    ) -> Optional[tuple[List[dict[str, Any]], List[dict[str, Any]]]]:
        """Parse rows using header-derived positions when word coordinates exist."""
        raw_rows: List[dict[str, Any]] = []
        unresolved: List[dict[str, Any]] = []
        active_anchors: Optional[dict[str, float]] = None
        last_transaction_page: Optional[int] = None
        last_transaction_y: Optional[float] = None
        date_regex = re.compile(
            r"^\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}$|^\d{1,2}\s+[A-Za-z]{3}\s+\d{4}$"
        )
        amount_regex = re.compile(r"^-?[0-9,]+\.\d{2}$")

        for page in pages_content:
            page_num = page.get("page_num", 1)
            method = page.get("method", "text")
            page_row_number = 0
            for word_row in page.get("word_rows") or []:
                if not word_row or not all("x0" in word and "x1" in word for word in word_row):
                    continue

                anchors = self._column_anchors(word_row)
                if anchors:
                    active_anchors = anchors
                    continue
                if not active_anchors:
                    continue

                date_words = [
                    word for word in word_row
                    if date_regex.match(str(word["text"]).strip())
                    and abs(
                        (float(word["x0"]) + float(word["x1"])) / 2
                        - active_anchors["date"]
                    ) < 100
                ]
                txn_date = min(
                    date_words,
                    key=lambda word: abs(
                        (float(word["x0"]) + float(word["x1"])) / 2
                        - active_anchors["date"]
                    ),
                    default=None,
                )

                def word_center(word: dict[str, Any]) -> float:
                    return (float(word["x0"]) + float(word["x1"])) / 2

                description_start = active_anchors["date"] + 20
                description_end = (
                    (active_anchors["description"] + active_anchors["reference"]) / 2
                    if "reference" in active_anchors
                    else (active_anchors["description"] + active_anchors["debit"]) / 2
                )
                description = " ".join(
                    str(word["text"])
                    for word in word_row
                    if description_start <= word_center(word) < description_end
                ).strip()

                if txn_date is None:
                    row_y = min(float(word["y0"]) for word in word_row)
                    is_continuation = (
                        raw_rows
                        and description
                        and page_num == last_transaction_page
                        and last_transaction_y is not None
                        and 0 < row_y - last_transaction_y <= 20
                    )
                    if is_continuation:
                        raw_rows[-1]["description"] = (
                            f"{raw_rows[-1]['description']} {description}"
                        ).strip()
                        raw_rows[-1]["raw_text"] = (
                            f"{raw_rows[-1]['raw_text']} {description}"
                        ).strip()
                        last_transaction_y = row_y
                    elif description and any(
                        amount_regex.fullmatch(str(word["text"]).replace(" ", ""))
                        for word in word_row
                    ):
                        unresolved.append({
                            "source_page": page_num,
                            "raw_text": " ".join(str(word["text"]) for word in word_row),
                            "reason": "Transaction-like row has amounts but no readable date.",
                            "extraction_method": method,
                        })
                    continue

                row_values: dict[str, list[str]] = {
                    "debit": [],
                    "credit": [],
                    "balance": [],
                }
                for word in word_row:
                    text = str(word["text"]).replace(" ", "")
                    if not amount_regex.fullmatch(text):
                        continue
                    column = min(
                        row_values,
                        key=lambda key: abs(word_center(word) - active_anchors[key]),
                    )
                    row_values[column].append(text)

                debit = row_values["debit"][-1] if row_values["debit"] else None
                credit = row_values["credit"][-1] if row_values["credit"] else None
                balance = row_values["balance"][-1] if row_values["balance"] else None
                if not debit and not credit and not balance:
                    line_text = " ".join(str(word["text"]) for word in word_row)
                    if not re.search(r"(?i)\bfrom\s*:", line_text):
                        unresolved.append({
                            "source_page": page_num,
                            "raw_text": line_text,
                            "reason": "Transaction row has no readable amounts.",
                            "extraction_method": method,
                        })
                    continue

                row_confidences = [
                    float(word["confidence"])
                    for word in word_row
                    if word.get("confidence") is not None
                ]
                page_row_number += 1
                raw_rows.append({
                    "source_page": page_num,
                    "source_row": page_row_number,
                    "extraction_method": method,
                    "date": str(txn_date["text"]),
                    "description": description,
                    "debit": debit,
                    "credit": credit,
                    "balance": balance,
                    "extraction_confidence": (
                        sum(row_confidences) / len(row_confidences) / 100
                        if row_confidences and max(row_confidences) > 1
                        else sum(row_confidences) / len(row_confidences)
                        if row_confidences
                        else None
                    ),
                    "raw_text": " ".join(str(word["text"]) for word in word_row),
                })
                last_transaction_page = page_num
                last_transaction_y = min(float(word["y0"]) for word in word_row)

        if active_anchors is None or (not raw_rows and not unresolved):
            return None
        return raw_rows, unresolved

    def _parse_transaction_id_ocr_page(
        self,
        lines: List[str],
        page_num: int,
        method: str,
    ) -> tuple[List[dict[str, Any]], List[dict[str, Any]]]:
        """Parse OCR statements whose transaction IDs precede their dates."""
        transaction_start = re.compile(
            r"^\s*([A-Za-z$#]?\s*\d{6,})\b\s*(.*)$"
        )
        date_pattern = re.compile(
            r"\b(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"
            r"|\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\b"
        )
        amount_pattern = re.compile(
            r"(?<![\w/])(?:\d{1,3}(?:,\d{2,3})+|\d+)\.\d{2}\b"
        )
        direction_pattern = re.compile(
            r"\(\s*(DR|CR)\s*\)|/(DR|CR)/|\b(DR|CR)\b",
            re.IGNORECASE,
        )

        blocks: List[dict[str, Any]] = []
        current_block: Optional[dict[str, Any]] = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            start_match = transaction_start.match(line)
            is_marked_transaction_id = line.startswith(("$", "#"))
            has_transaction_fields = bool(
                start_match
                and (
                    date_pattern.search(start_match.group(2))
                    or amount_pattern.search(start_match.group(2))
                )
            )
            date_match = date_pattern.search(line)
            has_amount = bool(amount_pattern.search(line))
            starts_without_id = bool(date_match and has_amount)
            if (
                (start_match and (is_marked_transaction_id or has_transaction_fields))
                or starts_without_id
            ):
                if current_block:
                    blocks.append(current_block)
                if start_match:
                    current_block = {
                        "reference_number": re.sub(r"\s+", "", start_match.group(1)),
                        "lines": [start_match.group(2).strip()],
                        "warnings": [],
                    }
                else:
                    current_block = {
                        "reference_number": None,
                        "lines": [line],
                        "warnings": ["Transaction ID could not be read by OCR."],
                    }
            elif current_block:
                current_block["lines"].append(line)

        if current_block:
            blocks.append(current_block)

        raw_rows: List[dict[str, Any]] = []
        unresolved: List[dict[str, Any]] = []
        for source_row, block in enumerate(blocks, start=1):
            block_lines = block["lines"]
            block_text = " ".join(block_lines)
            amounts = list(amount_pattern.finditer(block_text))
            date_match = date_pattern.search(block_text)
            txn_date = date_match.group(0) if date_match else None
            amount_match = amounts[-2] if len(amounts) >= 2 else (amounts[-1] if amounts else None)
            balance_match = amounts[-1] if len(amounts) >= 2 else None

            direction_match = direction_pattern.search(block_text)
            direction = direction_match.group(1) or direction_match.group(2) or direction_match.group(3) if direction_match else ""

            description_parts: List[str] = []
            offset = 0
            for line in block_lines:
                line_start = offset
                line_end = line_start + len(line)
                offset = line_end + 1
                fragments = [line]

                if date_match and line_start <= date_match.start() < line_end:
                    local_start = date_match.start() - line_start
                    local_end = date_match.end() - line_start
                    fragments = [
                        line[:local_start],
                        line[local_end:],
                    ]

                cleaned_fragments: List[str] = []
                for fragment in fragments:
                    fragment = amount_pattern.sub(" ", fragment)
                    fragment = direction_pattern.sub(" ", fragment)
                    fragment = re.sub(r"\s+", " ", fragment).strip(" \t:;,-")
                    if fragment:
                        cleaned_fragments.append(fragment)
                description_parts.extend(cleaned_fragments)

            description = " ".join(description_parts).strip()
            row_warnings = list(block.get("warnings") or [])
            if not txn_date:
                row_warnings.append("Transaction date could not be read by OCR.")
            if amount_match is None:
                row_warnings.append("Transaction amount could not be read by OCR.")
            if balance_match is None:
                row_warnings.append("Transaction balance could not be read by OCR.")
            raw_rows.append({
                "source_page": page_num,
                "source_row": source_row,
                "extraction_method": method,
                "date": txn_date,
                "description": description,
                "amount": amount_match.group(0) if amount_match else None,
                "balance": balance_match.group(0) if balance_match else None,
                "type": direction,
                "transaction_id": block["reference_number"],
                "reference_number": block["reference_number"],
                "warnings": row_warnings,
                "raw_text": " ".join(
                    [block["reference_number"], *block_lines]
                    if block["reference_number"]
                    else block_lines
                ).strip(),
            })

        candidate_ids = [
            row["reference_number"]
            for row in raw_rows
            if row.get("reference_number")
        ]
        dollar_prefix_count = sum(
            transaction_id.startswith("$") for transaction_id in candidate_ids
        )
        has_recurring_s_prefix = (
            candidate_ids
            and dollar_prefix_count > len(candidate_ids) / 2
        )
        for row in raw_rows:
            transaction_id = row.get("reference_number")
            if transaction_id and transaction_id.startswith("$"):
                row["reference_number"] = f"S{transaction_id[1:]}"
            elif (
                has_recurring_s_prefix
                and transaction_id
                and re.fullmatch(r"8\d{6,}", transaction_id)
            ):
                row["reference_number"] = f"S{transaction_id[1:]}"
                row["warnings"].append(
                    "Transaction ID prefix was corrected from a low-confidence OCR reading; verify against the source."
                )

        return raw_rows, unresolved

    def parse_transactions(
        self,
        pages_content: List[dict[str, Any]],
    ) -> tuple[List[dict[str, Any]], List[dict[str, Any]]]:
        coordinate_result = self._parse_coordinate_rows(pages_content)
        if coordinate_result is not None:
            return coordinate_result

        raw_rows: List[dict[str, Any]] = []
        unresolved: List[dict[str, Any]] = []
        has_transaction_id_ocr_layout = any(
            page.get("method") == "ocr"
            and re.search(
                r"\btran\s*id\b.*\btran\s*date\b.*\bamount\b.*\bbalance\b",
                " ".join(page.get("lines") or []),
                re.IGNORECASE,
            )
            for page in pages_content
        )

        date_regex = re.compile(r"^\b(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\b")

        for page in pages_content:
            page_num = page.get("page_num", 1)
            method = page.get("method", "text")
            if method == "ocr" and has_transaction_id_ocr_layout:
                page_rows, page_unresolved = self._parse_transaction_id_ocr_page(
                    page.get("lines") or [],
                    page_num,
                    method,
                )
                raw_rows.extend(page_rows)
                unresolved.extend(page_unresolved)
                continue

            tables = [t for t in page.get("tables", []) if self._is_usable_table(t)]

            # First priority: extracted structured tables (skip collapsed pdfplumber dumps)
            if tables:
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    # Find header row
                    header = [str(cell or "").lower() for cell in table[0]]
                    col_map: dict[str, int] = {}
                    for idx, h in enumerate(header):
                        if any(label in h for label in ("tran date", "transaction date", "date")):
                            col_map["date"] = idx
                        elif any(label in h for label in ("desc", "narration", "particular", "remarks")):
                            col_map["desc"] = idx
                        elif any(label in h for label in ("mode", "channel", "payment type")):
                            col_map["mode"] = idx
                        elif any(label in h for label in ("transaction id", "tran id", "txn id", "reference", "ref no", "cheque", "chq")):
                            col_map["ref"] = idx
                        elif any(label in h for label in ("debit", "withdrawal", "withdraw")):
                            col_map["debit"] = idx
                        elif any(label in h for label in ("credit", "deposit", "deposits")):
                            col_map["credit"] = idx
                        elif "balance" in h or "bal" in h:
                            col_map["balance"] = idx
                        elif "dr/cr" in h or "cr/dr" in h or "amount type" in h:
                            col_map["amount"] = idx
                            col_map["type"] = idx
                        elif "amount" in h:
                            col_map["amount"] = idx
                        elif h.strip() == "type":
                            col_map["type"] = idx

                    for table_row_number, row in enumerate(table[1:], start=1):
                        if not any(row):
                            continue
                        date_cell = row[col_map["date"]] if "date" in col_map and col_map["date"] < len(row) else None
                        desc_cell = row[col_map["desc"]] if "desc" in col_map and col_map["desc"] < len(row) else ""
                        debit_cell = row[col_map["debit"]] if "debit" in col_map and col_map["debit"] < len(row) else None
                        credit_cell = row[col_map["credit"]] if "credit" in col_map and col_map["credit"] < len(row) else None
                        bal_cell = row[col_map["balance"]] if "balance" in col_map and col_map["balance"] < len(row) else None
                        ref_cell = row[col_map["ref"]] if "ref" in col_map and col_map["ref"] < len(row) else None
                        amount_cell = row[col_map["amount"]] if "amount" in col_map and col_map["amount"] < len(row) else None
                        type_cell = row[col_map["type"]] if "type" in col_map and col_map["type"] < len(row) else None
                        mode_cell = row[col_map["mode"]] if "mode" in col_map and col_map["mode"] < len(row) else None
                        reference_cell = row[col_map["ref"]] if "ref" in col_map and col_map["ref"] < len(row) else None

                        raw_rows.append({
                            "source_page": page_num,
                            "source_row": table_row_number,
                            "extraction_method": method,
                            "date": date_cell,
                            "description": desc_cell or "",
                            "debit": debit_cell,
                            "credit": credit_cell,
                            "balance": bal_cell,
                            "amount": amount_cell,
                            "mode": mode_cell,
                            "transaction_id": reference_cell,
                            "type": " ".join(
                                value for value in (str(type_cell or ""), str(amount_cell or ""))
                                if value
                            ),
                            "reference_number": ref_cell or reference_cell,
                            "raw_text": " | ".join(str(c or "") for c in row),
                        })
            else:
                # Fallback: line-by-line regex parsing from page text
                lines = page.get("lines", [])
                page_row_number = 0
                for line in lines:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    m = date_regex.match(line_str)
                    if m:
                        # Extract tokens from line
                        tokens = line_str.split()
                        # Date is first token
                        d_token = m.group(0)
                        rest = line_str[len(d_token):].strip()

                        # Money candidates at the end of the line
                        money_matches = list(re.finditer(r"([0-9,]+\.[0-9]{2}(?:\s*(?:cr|dr))?)", rest, re.IGNORECASE))
                        if money_matches:
                            # Typically the last is balance, second-to-last is debit/credit
                            amounts = [match.group(1) for match in money_matches]
                            # Description is everything before the amounts
                            first_amt_start = money_matches[0].start()
                            desc = rest[:first_amt_start].strip()

                            amount = None
                            balance = None
                            direction = ""
                            if len(amounts) >= 2:
                                balance = amounts[-1]
                                amount = amounts[-2]
                                if re.search(r"\bcr\b", amount, re.IGNORECASE):
                                    direction = "CR"
                                elif re.search(r"\bdr\b", amount, re.IGNORECASE):
                                    direction = "DR"
                            elif len(amounts) == 1:
                                amount = amounts[0]
                                if re.search(r"\bcr\b", amount, re.IGNORECASE):
                                    direction = "CR"
                                elif re.search(r"\bdr\b", amount, re.IGNORECASE):
                                    direction = "DR"

                            page_row_number += 1
                            raw_rows.append({
                                "source_page": page_num,
                                "source_row": page_row_number,
                                "extraction_method": method,
                                "date": d_token,
                                "description": desc,
                                "amount": amount,
                                "balance": balance,
                                "type": direction,
                                "raw_text": line_str,
                            })
                        else:
                            unresolved.append({
                                "source_page": page_num,
                                "raw_text": line_str,
                                "reason": "Dated transaction-like line has no readable amount.",
                                "extraction_method": method,
                            })
                    else:
                        # Could be a continuation line or header/footer
                        if raw_rows:
                            if page_num == raw_rows[-1]["source_page"] and not re.search(
                                r"(?i)\b(?:date|particulars?|description|narration|debit|credit|withdrawals?|deposits?|balance|page\s+\d+|continued)\b",
                                line_str,
                            ):
                                raw_rows[-1]["description"] = (
                                    f"{raw_rows[-1].get('description', '')} {line_str}"
                                ).strip()
                                raw_rows[-1]["raw_text"] = (
                                    f"{raw_rows[-1].get('raw_text', '')} {line_str}"
                                ).strip()
                            else:
                                unresolved.append({
                                    "source_page": page_num,
                                    "raw_text": line_str,
                                    "reason": "Unparsed non-transaction line after transaction rows.",
                                    "extraction_method": method,
                                })
                        else:
                            unresolved.append({
                                "source_page": page_num,
                                "raw_text": line_str,
                                "reason": "Unrecognized line format before first transaction",
                                "extraction_method": method,
                            })

        return raw_rows, unresolved
