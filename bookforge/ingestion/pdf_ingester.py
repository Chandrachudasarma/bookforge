"""PDF ingester — Stage 1 for .pdf files.

Auto-detects scanned vs digital PDF and routes accordingly:
  Digital PDF  → PyMuPDF text extraction (preserves layout)
  Scanned PDF  → Tesseract OCR via OcrIngester

Detection heuristic: if average characters per sampled page < 100, treat as scanned.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

from bookforge.core.exceptions import IngestionError
from bookforge.core.models import Asset, RawContent
from bookforge.core.registry import get_ocr_engine, register_ingester
from bookforge.ingestion.base import BaseIngester

_SCANNED_THRESHOLD = 100  # avg chars per page below this → treat as scanned
_SAMPLE_PAGES = 3


@register_ingester("pdf")
class PdfIngester(BaseIngester):
    """Routes PDF files to digital extraction or OCR based on content."""

    supported_extensions = [".pdf"]
    supported_mimetypes = ["application/pdf"]

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".pdf"

    def ingest(self, file_path: Path, config: dict) -> RawContent:
        pdf_type = _detect_pdf_type(file_path)

        if pdf_type == "scanned":
            return self._ingest_scanned(file_path, config)
        else:
            return self._ingest_digital(file_path, config)

    def _ingest_digital(self, file_path: Path, config: dict) -> RawContent:
        """Extract text from a digital (text-based) PDF using PyMuPDF."""
        try:
            doc = fitz.open(str(file_path))
        except Exception as exc:
            raise IngestionError(f"Cannot open PDF: {file_path.name}: {exc}") from exc

        temp_dir = Path(config.get("pipeline", {}).get("temp_dir", "/tmp/bookforge"))
        temp_dir.mkdir(parents=True, exist_ok=True)

        html_parts: list[str] = []
        assets: list[Asset] = []
        img_counter = 0

        try:
            for page_num in range(len(doc)):
                page = doc[page_num]

                # Extract tables first (PyMuPDF find_tables gives structured data)
                page_tables_html = _extract_tables(page)

                # Extract text with basic HTML formatting
                page_html = page.get_text("html")
                if page_html.strip():
                    html_parts.append(f"<div class='pdf-page' data-page='{page_num + 1}'>{page_html}</div>")

                # Append detected tables as proper HTML tables
                if page_tables_html:
                    html_parts.append(page_tables_html)

                # Extract images from the page
                for img_info in page.get_images(full=True):
                    xref = img_info[0]
                    try:
                        base_image = doc.extract_image(xref)
                        img_bytes = base_image["image"]
                        img_ext = base_image["ext"]
                        img_name = f"pdf_img_{img_counter}.{img_ext}"
                        img_path = temp_dir / img_name
                        img_path.write_bytes(img_bytes)
                        media_type = f"image/{img_ext}"
                        assets.append(Asset(
                            filename=img_name,
                            media_type=media_type,
                            file_path=img_path,
                            size_bytes=len(img_bytes),
                        ))
                        img_counter += 1
                    except Exception:
                        pass  # skip unextractable images
        finally:
            doc.close()

        return RawContent(
            text="\n".join(html_parts),
            format_hint="html",
            assets=assets,
            source_metadata={"original_format": "pdf", "pdf_type": "digital"},
            source_path=file_path,
        )

    def _ingest_scanned(self, file_path: Path, config: dict) -> RawContent:
        """OCR a scanned PDF using the configured OCR engine."""
        ocr_config = config.get("ocr", {})
        engine_name = ocr_config.get("engine", "tesseract")
        language = ocr_config.get("language", "eng")
        dpi = ocr_config.get("dpi", 300)

        try:
            engine = get_ocr_engine(engine_name)
        except Exception as exc:
            raise IngestionError(f"OCR engine '{engine_name}' not available: {exc}") from exc

        page_results = engine.ocr_pdf(file_path, language=language, dpi=dpi)

        # Convert OCR text pages to basic HTML
        html_parts: list[str] = []
        for result in page_results:
            if result.text.strip():
                escaped = result.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                paragraphs = [
                    f"<p>{p.strip()}</p>"
                    for p in escaped.split("\n\n")
                    if p.strip()
                ]
                page_html = "\n".join(paragraphs)
                html_parts.append(
                    f"<div class='pdf-page' data-page='{result.page_num + 1}'>{page_html}</div>"
                )

        return RawContent(
            text="\n".join(html_parts),
            format_hint="html",
            assets=[],
            source_metadata={"original_format": "pdf", "pdf_type": "scanned", "pages": len(page_results)},
            source_path=file_path,
        )


# ---------------------------------------------------------------------------
# Table extraction
# ---------------------------------------------------------------------------


def _extract_tables(page) -> str:
    """Extract tables from a PDF page using PyMuPDF's find_tables().

    Returns HTML <table> elements, or empty string if no tables found.
    """
    try:
        tables = page.find_tables()
    except Exception:
        return ""

    if not tables.tables:
        return ""

    html_parts: list[str] = []
    for table in tables.tables:
        rows = table.extract()
        if not rows:
            continue

        table_html = ["<table>"]
        for i, row in enumerate(rows):
            tag = "th" if i == 0 else "td"
            cells = "".join(
                f"<{tag}>{_escape(str(cell or ''))}</{tag}>"
                for cell in row
            )
            wrap = "thead" if i == 0 else "tbody" if i == 1 else None
            if wrap == "thead":
                table_html.append(f"<thead><tr>{cells}</tr></thead><tbody>")
            elif i == len(rows) - 1:
                table_html.append(f"<tr>{cells}</tr></tbody>")
            else:
                table_html.append(f"<tr>{cells}</tr>")

        # Close tbody if only header row
        if len(rows) == 1:
            table_html.append("</tbody>")

        table_html.append("</table>")
        html_parts.append("\n".join(table_html))

    return "\n".join(html_parts)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def _detect_pdf_type(pdf_path: Path) -> str:
    """Return 'digital' or 'scanned' based on text content density."""
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        raise IngestionError(f"Cannot open PDF for type detection: {pdf_path.name}") from exc

    total_chars = 0
    pages_sampled = min(_SAMPLE_PAGES, len(doc))

    try:
        for page_num in range(pages_sampled):
            page = doc[page_num]
            text = page.get_text("text")
            total_chars += len(text.strip())
    finally:
        doc.close()

    if pages_sampled == 0:
        return "digital"

    avg_chars = total_chars / pages_sampled
    return "digital" if avg_chars >= _SCANNED_THRESHOLD else "scanned"
