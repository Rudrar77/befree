"""OCR extraction for scanned pages using OpenCV and Tesseract."""

from __future__ import annotations

import re
import shutil
from typing import Any, List, Optional, Tuple
import cv2
import numpy as np
from PIL import Image
import pytesseract


def is_tesseract_available() -> bool:
    """Check if tesseract binary is installed and executable."""
    return shutil.which("tesseract") is not None


def preprocess_image_for_ocr(pil_image: Image.Image) -> np.ndarray:
    """Preprocess image with OpenCV: grayscale, denoise, adaptive threshold, deskew.

    Args:
        pil_image: Input PIL Image

    Returns:
        Preprocessed image as NumPy array
    """
    # Convert PIL Image to OpenCV BGR format
    np_img = np.array(pil_image.convert("RGB"))
    img = cv2.cvtColor(np_img, cv2.COLOR_RGB2BGR)

    # 1. Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Denoise using fastNlMeansDenoising
    denoised = cv2.fastNlMeansDenoising(gray, h=10)

    # 3. Adaptive thresholding (Otsu's or Gaussian adaptive threshold)
    thresh = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )

    # 4. Deskew estimation using moments / minAreaRect
    try:
        coords = np.column_stack(np.where(thresh < 255))
        if len(coords) > 50:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            elif angle > 45:
                angle = 90 - angle
            else:
                angle = -angle

            if abs(angle) > 0.5 and abs(angle) < 45.0:
                (h, w) = thresh.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                thresh = cv2.warpAffine(
                    thresh, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
                )
    except Exception:
        pass

    return thresh


def extract_page_words_ocr(
    pil_image: Image.Image,
    dpi: int = 300,
) -> Tuple[List[dict[str, Any]], Optional[str]]:
    """Run OCR on a page image and return word bounding boxes matching PyMuPDF structure.

    Returns:
        tuple of (words: list[dict], error_message: str | None)
    """
    if not is_tesseract_available():
        return [], "Tesseract OCR binary is not installed or not in PATH."

    try:
        def _get_boxes(target_img: Any, page_segmentation_mode: int = 6) -> List[dict[str, Any]]:
            data = pytesseract.image_to_data(
                target_img,
                lang="eng",
                output_type=pytesseract.Output.DICT,
                config=f"--dpi {dpi} --psm {page_segmentation_mode}",
            )
            boxes: List[dict[str, Any]] = []
            n_boxes = len(data["text"])
            for i in range(n_boxes):
                word_text = data["text"][i].strip()
                conf = float(data["conf"][i])
                if not word_text or conf <= 0:
                    continue
                x = float(data["left"][i])
                y = float(data["top"][i])
                w = float(data["width"][i])
                h = float(data["height"][i])
                boxes.append({
                    "text": word_text,
                    "x0": x,
                    "y0": y,
                    "x1": x + w,
                    "y1": y + h,
                    "confidence": conf,
                    "block_no": int(data["block_num"][i]),
                    "line_no": int(data["line_num"][i]),
                })
            return boxes

        # 1. First attempt: standard image (preserves colored & watermarked text)
        words = _get_boxes(pil_image)

        # 2. If low word yield, fallback to OpenCV preprocessed thresholding
        if len(words) < 15:
            try:
                preprocessed = preprocess_image_for_ocr(pil_image)
                words_prep = _get_boxes(preprocessed)
                if len(words_prep) > len(words):
                    words = words_prep
            except Exception:
                pass

        # 3. Re-read the table as a separate region. Small table text, shaded
        # rows, and multiple columns are often missed by full-page PSM 6 OCR.
        header_rows: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for word in words:
            key = (word["block_no"], word["line_no"])
            header_rows.setdefault(key, []).append(word)

        table_header_y: float | None = None
        for row in header_rows.values():
            tokens = [word["text"].lower().strip("():.") for word in row]
            if (
                tokens.count("tran") >= 2
                and "date" in tokens
                and "amount" in tokens
                and "balance" in tokens
            ):
                table_header_y = min(float(word["y0"]) for word in row)
                break

        if table_header_y is not None:
            crop_top = max(0, int(table_header_y - 10))
            if pil_image.height - crop_top > 0.15 * pil_image.height:
                table_crop = pil_image.crop(
                    (0, crop_top, pil_image.width, pil_image.height)
                )
                table_words = _get_boxes(table_crop, page_segmentation_mode=4)
                if table_words:
                    def transaction_id_count(candidate_words: List[dict[str, Any]]) -> int:
                        candidate_lines: dict[tuple[int, int], list[str]] = {}
                        for candidate in candidate_words:
                            key = (
                                int(candidate.get("block_no", 0)),
                                int(candidate.get("line_no", 0)),
                            )
                            candidate_lines.setdefault(key, []).append(
                                str(candidate["text"])
                            )
                        return sum(
                            bool(
                                re.match(
                                    r"^[A-Za-z$#]?\d{6,}$",
                                    tokens[0],
                                )
                            )
                            for tokens in candidate_lines.values()
                        )

                    if transaction_id_count(table_words) < transaction_id_count(words):
                        return words, None

                    prefix_words = [
                        word for word in words
                        if float(word["y0"]) < crop_top
                    ]
                    for word in table_words:
                        word["y0"] += crop_top
                        word["y1"] += crop_top
                    words = prefix_words + table_words

        return words, None
    except Exception as exc:
        return [], f"OCR extraction failed: {str(exc)}"


class TesseractDocumentOCR:
    """Compatibility adapter for deployments explicitly selecting Tesseract."""

    def extract(self, pil_image: Image.Image) -> dict[str, Any]:
        words, error = extract_page_words_ocr(pil_image)
        if error:
            from app.extraction.document_ocr import OCRProviderError

            raise OCRProviderError(error)
        from app.extraction.table_extractor import cluster_words_into_rows, rows_to_text_lines

        rows = cluster_words_into_rows(words)
        return {
            "text": "\n".join(rows_to_text_lines(rows)),
            "words": words,
            "tables": [],
            "provider": "tesseract",
            "warnings": [],
        }
