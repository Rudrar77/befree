"""Provider adapters for document OCR and structure extraction."""

from __future__ import annotations

import html
import inspect
import io
import json
import logging
import os
import re
import threading
from difflib import SequenceMatcher
from html.parser import HTMLParser
from typing import Any, Protocol

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class OCRProviderError(RuntimeError):
    """Raised when an OCR provider is unavailable or rejects a document."""


def _format_exception_chain(exc: BaseException) -> str:
    parts: list[str] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = str(current).strip().replace("\n", " ")
        parts.append(f"{type(current).__name__}: {message}" if message else type(current).__name__)
        current = current.__cause__ or current.__context__
    return "; caused by ".join(parts)


def ensure_paddle_structure_dependencies() -> None:
    """PaddleOCR's PP-StructureV3 import succeeds without the PaddleX OCR extra."""
    try:
        from paddlex.utils.deps import is_extra_available
    except Exception:
        return
    if is_extra_available("ocr"):
        return
    raise OCRProviderError(
        "PaddleOCR PP-StructureV3 requires the PaddleX OCR extra "
        "(einops, ftfy, latex2mathml, premailer, tiktoken, tokenizers). "
        "Install it with 'python -m pip install -r requirements-ocr-paddle.txt'."
    )


def _normalized_confidence(words: list[dict[str, Any]]) -> float | None:
    confidences = [
        float(word["confidence"])
        for word in words
        if word.get("confidence") is not None
    ]
    if not confidences:
        return None
    average = sum(confidences) / len(confidences)
    return average / 100 if average > 1 else average


def compare_ocr_results(
    primary: dict[str, Any], secondary: dict[str, Any]
) -> list[str]:
    """Compare providers without merging potentially conflicting financial text."""
    first = re.sub(r"\s+", " ", (primary.get("text") or "").lower()).strip()
    second = re.sub(r"\s+", " ", (secondary.get("text") or "").lower()).strip()
    if not first or not second:
        return ["Independent OCR verification was incomplete; review this page."]
    if SequenceMatcher(None, first, second).ratio() < 0.9:
        return ["OCR providers disagreed on page text; values were not automatically merged."]
    first_tables = sum(len(table) for table in primary.get("tables") or [])
    second_tables = sum(len(table) for table in secondary.get("tables") or [])
    if abs(first_tables - second_tables) > 1:
        return ["OCR providers disagreed on table row count; review this page."]
    return []


class DocumentOCR(Protocol):
    def extract(self, image: Image.Image) -> dict[str, Any]:
        """Return page text, positioned words, and detected tables."""


class _TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(re.sub(r"\s+", " ", html.unescape(" ".join(self._cell))).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "json"):
        payload = value.json
        if callable(payload):
            payload = payload()
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return {}
        if isinstance(payload, dict):
            return payload
    return {}


def _flatten_ocr_results(value: Any) -> list[dict[str, Any]]:
    """Convert PP-Structure OCR polygons into the common word representation."""
    data = _as_mapping(value)
    if "res" in data and isinstance(data["res"], dict):
        data = data["res"]

    candidates: list[dict[str, Any]] = []
    for key in ("overall_ocr_res", "ocr_res", "text_recognition_res"):
        found = data.get(key)
        if isinstance(found, dict):
            candidates.append(found)
    if not candidates:
        candidates.append(data)

    words: list[dict[str, Any]] = []
    for result in candidates:
        texts = result.get("rec_texts")
        if texts is None:
            texts = result.get("texts") or []
        polygons = result.get("rec_polys")
        if polygons is None:
            polygons = result.get("dt_polys")
        if polygons is None:
            polygons = result.get("boxes") or []
        scores = result.get("rec_scores")
        if scores is None:
            scores = result.get("scores") or []
        for index, text in enumerate(texts):
            if index >= len(polygons) or not str(text).strip():
                continue
            points = np.asarray(polygons[index], dtype=float).reshape(-1, 2)
            if not len(points):
                continue
            words.append({
                "text": str(text).strip(),
                "x0": float(points[:, 0].min()),
                "y0": float(points[:, 1].min()),
                "x1": float(points[:, 0].max()),
                "y1": float(points[:, 1].max()),
                "confidence": float(scores[index]) if index < len(scores) else None,
                "block_no": 0,
                "line_no": index,
            })
    return words


def _named_callable_parameters(func: Any) -> set[str]:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return set()
    return {
        name
        for name, param in signature.parameters.items()
        if name != "self"
        and param.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }


def _filter_named_kwargs(func: Any, candidates: dict[str, Any], *, extra: set[str] | None = None) -> dict[str, Any]:
    """Keep only constructor arguments the installed PaddleOCR version documents."""
    allowed = _named_callable_parameters(func) | (extra or set())
    return {
        key: value
        for key, value in candidates.items()
        if key in allowed and value is not None
    }


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def ppstructure_v3_init_kwargs(pipeline_cls: Any, *, use_gpu: bool) -> dict[str, Any]:
    """Build PP-StructureV3 kwargs compatible with PaddleOCR 3.0–3.7."""
    table_model = os.environ.get("PADDLE_TABLE_MODEL", "SLANet_plus")
    wired_table_model = os.environ.get("PADDLE_WIRED_TABLE_MODEL", table_model)
    wireless_table_model = os.environ.get("PADDLE_WIRELESS_TABLE_MODEL", table_model)
    candidates = {
        "use_doc_orientation_classify": _env_flag("PADDLE_USE_DOC_ORIENTATION", False),
        "use_doc_unwarping": _env_flag("PADDLE_USE_UNWARPING", False),
        "use_textline_orientation": _env_flag("PADDLE_USE_TEXTLINE_ORIENTATION", False),
        "use_region_detection": _env_flag("PADDLE_USE_REGION_DETECTION", False),
        "use_table_recognition": True,
        "use_formula_recognition": False,
        "use_chart_recognition": False,
        "use_seal_recognition": False,
        "text_detection_model_name": os.environ.get(
            "PADDLE_TEXT_DETECTION_MODEL", "PP-OCRv4_mobile_det"
        ),
        "text_recognition_model_name": os.environ.get(
            "PADDLE_TEXT_RECOGNITION_MODEL", "en_PP-OCRv4_mobile_rec"
        ),
        "layout_detection_model_name": os.environ.get(
            "PADDLE_LAYOUT_MODEL", "PP-DocLayout_plus-L"
        ),
        "table_structure_recognition_model_name": table_model,
        "wired_table_structure_recognition_model_name": wired_table_model,
        "wireless_table_structure_recognition_model_name": wireless_table_model,
        "device": "gpu:0" if use_gpu else "cpu",
    }
    # `device` is accepted via **kwargs; unknown names such as the old
    # table_structure_recognition_model_name must not be forwarded.
    return _filter_named_kwargs(pipeline_cls, candidates, extra={"device"})


def _extract_tables(value: Any) -> list[list[list[str]]]:
    data = _as_mapping(value)
    if "res" in data and isinstance(data["res"], dict):
        data = data["res"]
    tables: list[list[list[str]]] = []
    for table in data.get("table_res_list") or []:
        table_data = _as_mapping(table)
        markup = table_data.get("pred_html") or table_data.get("html")
        if markup:
            parser = _TableHTMLParser()
            parser.feed(str(markup))
            if parser.rows:
                tables.append(parser.rows)
        elif table_data.get("cell_texts") and table_data.get("rows"):
            tables.append(table_data["rows"])
    return tables


class PaddleStructureV3OCR:
    """Lazy, process-wide PaddleOCR PP-StructureV3 document pipeline."""

    _pipeline: Any = None
    _lock = threading.Lock()

    def __init__(self, *, use_gpu: bool = False) -> None:
        self.use_gpu = use_gpu

    def _get_pipeline(self) -> Any:
        if self.__class__._pipeline is None:
            with self.__class__._lock:
                if self.__class__._pipeline is None:
                    try:
                        from paddleocr import PPStructureV3
                    except Exception as exc:
                        raise OCRProviderError(
                            "PaddleOCR PP-StructureV3 is unavailable "
                            f"({_format_exception_chain(exc)}). Install it with "
                            "'python -m pip install -r requirements-ocr-paddle.txt'."
                        ) from exc
                    try:
                        ensure_paddle_structure_dependencies()
                        logger.info("Initializing PaddleOCR PP-StructureV3 pipeline")
                        self.__class__._pipeline = PPStructureV3(
                            **ppstructure_v3_init_kwargs(PPStructureV3, use_gpu=self.use_gpu)
                        )
                        logger.info("PaddleOCR PP-StructureV3 pipeline is ready")
                    except OCRProviderError:
                        raise
                    except Exception as exc:
                        logger.exception("Could not initialize PaddleOCR PP-StructureV3")
                        raise OCRProviderError(
                            "PaddleOCR PP-StructureV3 initialization failed "
                            f"({_format_exception_chain(exc)}). Check model names, model download "
                            "connectivity, the configured Paddle device, and "
                            "'python -m pip install -r requirements-ocr-paddle.txt'."
                        ) from exc
        return self.__class__._pipeline

    def extract(self, image: Image.Image) -> dict[str, Any]:
        pipeline = self._get_pipeline()
        logger.info("Running PaddleOCR on %sx%s page image", image.width, image.height)
        try:
            predict_kwargs = _filter_named_kwargs(
                pipeline.predict,
                {
                    "input": np.asarray(image.convert("RGB")),
                    "use_e2e_wired_table_rec_model": True,
                    "use_e2e_wireless_table_rec_model": True,
                },
                extra={"input"},
            )
            results = pipeline.predict(**predict_kwargs)
            result_list = list(results) if results is not None else []
            logger.info("PaddleOCR finished page image with %s result group(s)", len(result_list))
        except Exception as exc:
            logger.exception("PP-StructureV3 inference failed")
            raise OCRProviderError(
                f"PaddleOCR PP-StructureV3 could not process this page "
                f"({type(exc).__name__}: {exc})."
            ) from exc

        words: list[dict[str, Any]] = []
        tables: list[list[list[str]]] = []
        for result in result_list:
            words.extend(_flatten_ocr_results(result))
            tables.extend(_extract_tables(result))

        from app.extraction.table_extractor import cluster_words_into_rows, rows_to_text_lines

        text = "\n".join(rows_to_text_lines(cluster_words_into_rows(words, y_tolerance=3)))
        return {
            "text": text,
            "words": words,
            "tables": tables,
            "provider": "paddleocr",
            "warnings": [],
        }


class AzureLayoutOCR:
    def __init__(self) -> None:
        endpoint = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
        key = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY")
        if not endpoint or not key:
            raise OCRProviderError(
                "Azure OCR requires AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and "
                "AZURE_DOCUMENT_INTELLIGENCE_KEY."
            )
        try:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.core.credentials import AzureKeyCredential
        except ImportError as exc:
            raise OCRProviderError("Install requirements-ocr-azure.txt to use Azure OCR.") from exc
        self.client = DocumentIntelligenceClient(endpoint, AzureKeyCredential(key))

    def extract(self, image: Image.Image) -> dict[str, Any]:
        data = io.BytesIO()
        image.save(data, format="PNG")
        try:
            result = self.client.begin_analyze_document(
                "prebuilt-layout", body=data.getvalue(), content_type="image/png"
            ).result()
        except Exception as exc:
            raise OCRProviderError("Azure Document Intelligence failed to process this page.") from exc

        words: list[dict[str, Any]] = []
        for page_index, page in enumerate(getattr(result, "pages", []) or []):
            for word_index, word in enumerate(getattr(page, "words", []) or []):
                polygon = getattr(word, "polygon", None) or []
                points = [(polygon[i], polygon[i + 1]) for i in range(0, len(polygon) - 1, 2)]
                if points:
                    words.append({
                        "text": word.content,
                        "x0": min(x for x, _ in points),
                        "y0": min(y for _, y in points),
                        "x1": max(x for x, _ in points),
                        "y1": max(y for _, y in points),
                        "confidence": getattr(word, "confidence", None),
                        "block_no": page_index,
                        "line_no": word_index,
                    })
        tables = []
        for table in getattr(result, "tables", []) or []:
            rows = [["" for _ in range(table.column_count)] for _ in range(table.row_count)]
            for cell in table.cells:
                rows[cell.row_index][cell.column_index] = cell.content or ""
            tables.append(rows)
        return {
            "text": getattr(result, "content", "") or "",
            "words": words,
            "tables": tables,
            "provider": "azure",
            "warnings": [],
        }


class GoogleDocumentAIOCR:
    def __init__(self) -> None:
        processor = os.environ.get("GOOGLE_DOCUMENTAI_PROCESSOR_NAME")
        if not processor:
            raise OCRProviderError("Google OCR requires GOOGLE_DOCUMENTAI_PROCESSOR_NAME.")
        try:
            from google.api_core.client_options import ClientOptions
            from google.cloud import documentai
        except ImportError as exc:
            raise OCRProviderError("Install requirements-ocr-google.txt to use Google OCR.") from exc
        endpoint = processor.split("/")[3] + "-documentai.googleapis.com"
        self.documentai = documentai
        self.client = documentai.DocumentProcessorServiceClient(
            client_options=ClientOptions(api_endpoint=endpoint)
        )
        self.processor = processor

    def extract(self, image: Image.Image) -> dict[str, Any]:
        data = io.BytesIO()
        image.save(data, format="PNG")
        try:
            response = self.client.process_document(
                request={
                    "name": self.processor,
                    "raw_document": self.documentai.RawDocument(
                        content=data.getvalue(), mime_type="image/png"
                    ),
                }
            )
        except Exception as exc:
            raise OCRProviderError("Google Document AI failed to process this page.") from exc

        document = response.document
        words: list[dict[str, Any]] = []
        for page_index, page in enumerate(document.pages):
            for token_index, token in enumerate(page.tokens):
                anchor = token.layout.text_anchor
                text = "".join(
                    document.text[segment.start_index:segment.end_index]
                    for segment in anchor.text_segments
                )
                vertices = token.layout.bounding_poly.normalized_vertices
                if text and vertices:
                    words.append({
                        "text": text,
                        "x0": min(vertex.x for vertex in vertices) * image.width,
                        "y0": min(vertex.y for vertex in vertices) * image.height,
                        "x1": max(vertex.x for vertex in vertices) * image.width,
                        "y1": max(vertex.y for vertex in vertices) * image.height,
                        "confidence": token.layout.confidence,
                        "block_no": page_index,
                        "line_no": token_index,
                    })
        tables = []
        for page in document.pages:
            for table in page.tables:
                rows = []
                for row in list(table.header_rows) + list(table.body_rows):
                    cells = []
                    for cell in row.cells:
                        anchor = cell.layout.text_anchor
                        cells.append("".join(
                            document.text[segment.start_index:segment.end_index]
                            for segment in anchor.text_segments
                        ))
                    rows.append(cells)
                if rows:
                    tables.append(rows)
        return {
            "text": document.text or "",
            "words": words,
            "tables": tables,
            "provider": "google",
            "warnings": [],
        }


class TextractOCR:
    def __init__(self) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise OCRProviderError("Install requirements-ocr-textract.txt to use AWS Textract.") from exc
        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
        if not region:
            raise OCRProviderError("AWS Textract requires AWS_REGION or AWS_DEFAULT_REGION.")
        self.client = boto3.client("textract", region_name=region)

    def extract(self, image: Image.Image) -> dict[str, Any]:
        data = io.BytesIO()
        image.save(data, format="PNG")
        try:
            response = self.client.analyze_document(
                Document={"Bytes": data.getvalue()}, FeatureTypes=["TABLES"]
            )
        except Exception as exc:
            raise OCRProviderError("AWS Textract failed to process this page.") from exc

        blocks = {block["Id"]: block for block in response.get("Blocks", [])}
        words: list[dict[str, Any]] = []
        for index, block in enumerate(blocks.values()):
            if block.get("BlockType") not in {"WORD", "LINE"}:
                continue
            box = block.get("Geometry", {}).get("BoundingBox", {})
            if not box:
                continue
            words.append({
                "text": block.get("Text", ""),
                "x0": box.get("Left", 0) * image.width,
                "y0": box.get("Top", 0) * image.height,
                "x1": (box.get("Left", 0) + box.get("Width", 0)) * image.width,
                "y1": (box.get("Top", 0) + box.get("Height", 0)) * image.height,
                "confidence": (block.get("Confidence", 0) / 100) if block.get("Confidence") is not None else None,
                "block_no": 0,
                "line_no": index,
            })
        tables = []
        for table in (block for block in blocks.values() if block.get("BlockType") == "TABLE"):
            cells = []
            for relation in table.get("Relationships", []):
                if relation.get("Type") != "CHILD":
                    continue
                cells.extend(
                    blocks[cell_id]
                    for cell_id in relation.get("Ids", [])
                    if cell_id in blocks and blocks[cell_id].get("BlockType") == "CELL"
                )
            if not cells:
                continue
            row_count = max(cell.get("RowIndex", 0) for cell in cells)
            col_count = max(cell.get("ColumnIndex", 0) for cell in cells)
            rows = [["" for _ in range(col_count)] for _ in range(row_count)]
            for cell in cells:
                value = []
                for relation in cell.get("Relationships", []):
                    if relation.get("Type") == "CHILD":
                        value.extend(
                            blocks[word_id].get("Text", "")
                            for word_id in relation.get("Ids", [])
                            if word_id in blocks
                        )
                rows[cell["RowIndex"] - 1][cell["ColumnIndex"] - 1] = " ".join(value)
            tables.append(rows)
        return {
            "text": "\n".join(
                block.get("Text", "") for block in blocks.values() if block.get("BlockType") == "LINE"
            ),
            "words": words,
            "tables": tables,
            "provider": "textract",
            "warnings": [],
        }


def get_document_ocr(provider: str, *, use_gpu: bool = False) -> DocumentOCR:
    """Build the configured OCR provider without importing optional SDKs eagerly."""
    normalized = provider.strip().lower()
    if normalized == "paddleocr":
        return PaddleStructureV3OCR(use_gpu=use_gpu)
    if normalized == "tesseract":
        from app.extraction.ocr_extractor import TesseractDocumentOCR

        return TesseractDocumentOCR()
    if normalized == "azure":
        return AzureLayoutOCR()
    if normalized == "google":
        return GoogleDocumentAIOCR()
    if normalized == "textract":
        return TextractOCR()
    raise OCRProviderError(f"Unsupported OCR_PROVIDER '{provider}'.")


def extract_with_fallback(
    image: Image.Image,
    provider: str,
    fallback_provider: str,
    *,
    use_gpu: bool = False,
) -> dict[str, Any]:
    """Use the configured backup only after a primary provider failure."""
    try:
        return get_document_ocr(provider, use_gpu=use_gpu).extract(image)
    except OCRProviderError as primary_error:
        fallback = fallback_provider.strip().lower()
        if not fallback or fallback == provider.strip().lower():
            raise
        logger.warning(
            "Primary OCR provider '%s' failed; trying fallback '%s': %s",
            provider,
            fallback,
            primary_error,
        )
        result = get_document_ocr(fallback, use_gpu=use_gpu).extract(image)
        result.setdefault("warnings", []).append(
            f"Primary OCR provider '{provider}' failed ({primary_error}); "
            f"fallback '{fallback}' was used. "
            "Review the extracted rows and amounts."
        )
        return result


def verify_ocr_result(
    image: Image.Image,
    primary: dict[str, Any],
    provider: str | None,
    *,
    use_gpu: bool = False,
) -> list[str]:
    """Run an explicitly configured second provider only for weak primary output."""
    if not provider or provider.strip().lower() == primary.get("provider"):
        return []
    confidence = _normalized_confidence(primary.get("words") or [])
    if len(primary.get("words") or []) >= 20 and (confidence is None or confidence >= 0.65):
        return []
    secondary = get_document_ocr(provider, use_gpu=use_gpu).extract(image)
    return compare_ocr_results(primary, secondary)
