"""OCR ingester — Stage 1 for scanned image files.

Handles TIFF, PNG, JPEG, and BMP formats via the configured OCR engine.
All four scanned image formats the client requires route through here.
"""

from __future__ import annotations

from pathlib import Path

from bookforge.core.exceptions import IngestionError
from bookforge.core.models import RawContent
from bookforge.core.registry import get_ocr_engine, register_ingester
from bookforge.ingestion.base import BaseIngester

_IMAGE_EXTENSIONS = {".tiff", ".tif", ".png", ".jpg", ".jpeg", ".bmp"}


@register_ingester("ocr")
class OcrIngester(BaseIngester):
    """OCR-based ingester for scanned image files."""

    supported_extensions = list(_IMAGE_EXTENSIONS)
    supported_mimetypes = ["image/tiff", "image/png", "image/jpeg", "image/bmp"]

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in _IMAGE_EXTENSIONS

    def ingest(self, file_path: Path, config: dict) -> RawContent:
        ocr_config = config.get("ocr", {})
        engine_name = ocr_config.get("engine", "tesseract")
        language = ocr_config.get("language", "eng")
        psm = ocr_config.get("page_segmentation_mode", 6)

        try:
            engine = get_ocr_engine(engine_name)
        except Exception as exc:
            raise IngestionError(f"OCR engine '{engine_name}' not available: {exc}") from exc

        text = engine.ocr_image(file_path, language=language, psm=psm)

        # Convert plain OCR text to basic HTML
        html_parts: list[str] = []
        for paragraph in text.split("\n\n"):
            stripped = paragraph.strip()
            if stripped:
                escaped = stripped.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_parts.append(f"<p>{escaped}</p>")

        html = "\n".join(html_parts) or "<p></p>"

        return RawContent(
            text=html,
            format_hint="html",
            assets=[],
            source_metadata={"original_format": "ocr_image", "ocr_engine": engine_name},
            source_path=file_path,
        )
