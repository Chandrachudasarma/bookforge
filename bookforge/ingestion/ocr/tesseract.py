"""Tesseract OCR engine implementation.

Known limitation: Tesseract cannot reconstruct equations from scanned images.
Mathematical notation will appear as garbled text in the output. For
math-heavy scanned content, use digital source files or Mathpix pre-processing.
See SETUP.md for details.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from bookforge.core.exceptions import IngestionError
from bookforge.core.registry import register_ocr_engine
from bookforge.ingestion.ocr.base import BaseOCREngine, PageResult


@register_ocr_engine("tesseract")
class TesseractOCREngine(BaseOCREngine):
    """OCR via Tesseract (pytesseract wrapper)."""

    def ocr_image(self, image_path: Path, language: str = "eng", *, psm: int = 6, **kwargs) -> str:
        """OCR a single image file.

        Args:
            image_path: Path to TIFF, PNG, JPEG, or BMP file.
            language:   Tesseract language code (default: "eng").
            psm:        Page segmentation mode (default: 6 = uniform block of text).
                        Common values: 3=auto, 6=uniform block, 11=sparse text.
        """
        try:
            img = Image.open(image_path)
        except Exception as exc:
            raise IngestionError(f"Cannot open image for OCR: {image_path.name}") from exc

        # Grayscale improves Tesseract accuracy on most documents
        img = img.convert("L")

        try:
            text = pytesseract.image_to_string(
                img,
                lang=language,
                config=f"--psm {psm}",
            )
        except pytesseract.TesseractNotFoundError as exc:
            raise IngestionError(
                "Tesseract is not installed. Install it with: brew install tesseract"
            ) from exc
        except Exception as exc:
            raise IngestionError(f"OCR failed for {image_path.name}: {exc}") from exc

        return text

    def ocr_pdf(self, pdf_path: Path, language: str = "eng", *, dpi: int = 300, **kwargs) -> list[PageResult]:
        """OCR all pages of a scanned PDF.

        Each page is rendered to a PNG at the specified DPI and then OCR'd.
        The PNG is written to a temp file to avoid memory accumulation.
        """
        try:
            doc = fitz.open(str(pdf_path))
        except Exception as exc:
            raise IngestionError(f"Cannot open PDF for OCR: {pdf_path.name}") from exc

        results: list[PageResult] = []
        temp_dir = pdf_path.parent / "_ocr_temp"
        temp_dir.mkdir(exist_ok=True)

        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                # Render page to image at specified DPI
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat, alpha=False)

                img_path = temp_dir / f"page_{page_num:04d}.png"
                pix.save(str(img_path))

                text = self.ocr_image(img_path, language=language)
                results.append(PageResult(page_num=page_num, text=text))

                img_path.unlink(missing_ok=True)  # clean up immediately
        finally:
            doc.close()
            # Clean up temp dir if empty
            try:
                temp_dir.rmdir()
            except OSError:
                pass

        return results
