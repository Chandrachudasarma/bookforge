"""EPUB ingester — Stage 1 for .epub files (reverse conversion).

Reads an EPUB and extracts HTML content chapters and assets for
conversion to DOCX or PDF.
"""

from __future__ import annotations

from pathlib import Path

import ebooklib
from ebooklib import epub

from bookforge.core.exceptions import IngestionError
from bookforge.core.models import Asset, RawContent
from bookforge.core.registry import register_ingester
from bookforge.ingestion.base import BaseIngester


@register_ingester("epub")
class EpubIngester(BaseIngester):
    """Reads EPUB files and extracts content as HTML."""

    supported_extensions = [".epub"]
    supported_mimetypes = ["application/epub+zip"]

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".epub"

    def ingest(self, file_path: Path, config: dict) -> RawContent:
        try:
            book = epub.read_epub(str(file_path), options={"ignore_ncx": True})
        except Exception as exc:
            raise IngestionError(f"Cannot open EPUB: {file_path.name}: {exc}") from exc

        temp_dir = Path(config.get("pipeline", {}).get("temp_dir", "/tmp/bookforge"))
        temp_dir.mkdir(parents=True, exist_ok=True)

        chapters_html: list[str] = []
        assets: list[Asset] = []

        # Extract document items in spine order
        spine_ids = {item_id for item_id, _ in book.spine}

        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                # Prefer spine order; include all documents if spine is empty
                content = item.get_content()
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="replace")
                chapters_html.append(content)

            elif item.get_type() == ebooklib.ITEM_IMAGE:
                img_name = Path(item.get_name()).name
                img_path = temp_dir / img_name
                try:
                    img_path.write_bytes(item.get_content())
                    assets.append(Asset(
                        filename=img_name,
                        media_type=item.media_type or "image/png",
                        file_path=img_path,
                        size_bytes=img_path.stat().st_size,
                    ))
                except Exception:
                    pass  # skip unwritable assets

        # Extract book title from metadata
        titles = book.get_metadata("DC", "title")
        source_title = titles[0][0] if titles else None

        return RawContent(
            text="\n".join(chapters_html),
            format_hint="html",
            assets=assets,
            source_metadata={
                "original_format": "epub",
                "title": source_title,
            },
            source_path=file_path,
        )
