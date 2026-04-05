"""Abstract base class for OCR engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PageResult:
    """OCR result for a single page."""
    page_num: int
    text: str
    confidence: float = 0.0


class BaseOCREngine(ABC):
    """Converts images and scanned documents to text."""

    @abstractmethod
    def ocr_image(self, image_path: Path, language: str, **kwargs) -> str:
        """OCR a single image file. Return extracted text.

        Engine-specific keyword arguments (e.g. psm for Tesseract) are
        passed through via **kwargs.
        """

    @abstractmethod
    def ocr_pdf(self, pdf_path: Path, language: str, **kwargs) -> list[PageResult]:
        """OCR a scanned PDF. Return per-page results.

        Engine-specific keyword arguments (e.g. dpi for Tesseract) are
        passed through via **kwargs.
        """
