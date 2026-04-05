"""HTML ingester — Stage 1 for .html / .htm files."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import chardet
from bs4 import BeautifulSoup

from bookforge.core.exceptions import IngestionError
from bookforge.core.models import Asset, RawContent
from bookforge.core.registry import register_ingester
from bookforge.ingestion.base import BaseIngester


@register_ingester("html")
class HtmlIngester(BaseIngester):
    """Reads HTML files and extracts content + embedded assets."""

    supported_extensions = [".html", ".htm"]
    supported_mimetypes = ["text/html"]

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.supported_extensions

    def ingest(self, file_path: Path, config: dict) -> RawContent:
        """Read the HTML file and return RawContent.

        Images referenced by relative src paths are copied to the temp
        directory and returned as file-backed Assets.
        """
        try:
            raw_bytes = file_path.read_bytes()
        except OSError as exc:
            raise IngestionError(f"Cannot read file: {file_path}") from exc

        # Detect encoding
        encoding = _detect_encoding(raw_bytes)
        try:
            html_text = raw_bytes.decode(encoding, errors="replace")
        except (LookupError, UnicodeDecodeError):
            html_text = raw_bytes.decode("utf-8", errors="replace")

        temp_dir = Path(config.get("pipeline", {}).get("temp_dir", "/tmp/bookforge"))
        assets = _extract_assets(html_text, file_path, temp_dir)

        return RawContent(
            text=html_text,
            format_hint="html",
            assets=assets,
            source_metadata={"encoding": encoding, "original_size": len(raw_bytes)},
            source_path=file_path,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_encoding(raw_bytes: bytes) -> str:
    """Detect file encoding; default to utf-8."""
    # Try BOM first
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw_bytes.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if raw_bytes.startswith(b"\xfe\xff"):
        return "utf-16-be"

    # Check <meta charset="...">
    head = raw_bytes[:2048].decode("ascii", errors="ignore")
    m = re.search(r'charset=["\']?([\w-]+)', head, re.IGNORECASE)
    if m:
        return m.group(1)

    # chardet fallback
    result = chardet.detect(raw_bytes[:4096])
    return result.get("encoding") or "utf-8"


def _extract_assets(html: str, source_file: Path, temp_dir: Path) -> list[Asset]:
    """Extract locally referenced images and copy them to temp_dir."""
    assets: list[Asset] = []
    soup = BeautifulSoup(html, "lxml")

    for img in soup.find_all("img", src=True):
        src = img["src"]
        parsed = urlparse(src)

        # Skip data URIs and absolute URLs
        if parsed.scheme in ("http", "https", "data", "ftp"):
            continue

        img_path = (source_file.parent / src).resolve()
        if not img_path.exists():
            continue

        suffix = img_path.suffix.lower()
        media_type = _image_media_type(suffix)
        if not media_type:
            continue

        content = img_path.read_bytes()
        filename = _stable_filename(src, suffix)
        dest = temp_dir / filename
        temp_dir.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)

        assets.append(
            Asset(
                filename=filename,
                media_type=media_type,
                file_path=dest,
                size_bytes=len(content),
            )
        )

    return assets


def _image_media_type(suffix: str) -> str | None:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
    }.get(suffix)


def _stable_filename(src: str, suffix: str) -> str:
    """Generate a stable filename from the src path."""
    h = hashlib.md5(src.encode()).hexdigest()[:8]
    stem = Path(src).stem[:20].replace(" ", "_")
    return f"{stem}_{h}{suffix}"
