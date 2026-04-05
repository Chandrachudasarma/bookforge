"""File format detection.

Detection order:
1. File extension (fast, reliable for well-named files)
2. Magic bytes (for files without extensions or misnamed files)
3. MIME type sniffing via the `file` command (fallback)

For PDFs: separate scanned-vs-digital detection is done inside
PdfIngester — this module only returns "pdf".
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from bookforge.core.exceptions import IngestionError

# Extension → format name
_EXT_MAP: dict[str, str] = {
    ".html": "html",
    ".htm": "html",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "txt",
    ".text": "txt",
    ".docx": "docx",
    ".pdf": "pdf",
    ".epub": "epub",
    ".tiff": "ocr",
    ".tif": "ocr",
    ".png": "ocr",
    ".jpg": "ocr",
    ".jpeg": "ocr",
    ".bmp": "ocr",
}

# Magic bytes → format name
_MAGIC_MAP: list[tuple[bytes, str]] = [
    (b"%PDF", "pdf"),
    (b"PK\x03\x04", "docx"),   # DOCX is a ZIP; EPUB too — disambiguate below
    (b"<?xml", "html"),
    (b"<html", "html"),
    (b"<!DOCTYPE", "html"),
]


def detect_format(file_path: Path) -> str:
    """Return a format name for the given file.

    Raises IngestionError if the format cannot be determined.
    """
    ext = file_path.suffix.lower()
    if ext in _EXT_MAP:
        return _EXT_MAP[ext]

    # Fall back to magic bytes
    try:
        header = file_path.read_bytes()[:16]
    except OSError as exc:
        raise IngestionError(f"Cannot read file: {file_path}") from exc

    for magic, fmt in _MAGIC_MAP:
        if header.startswith(magic):
            if fmt == "docx":
                # Distinguish DOCX from EPUB — both are ZIP-based
                return _disambiguate_zip(file_path)
            return fmt

    # Last resort: MIME type
    mime, _ = mimetypes.guess_type(str(file_path))
    if mime:
        if "html" in mime:
            return "html"
        if "pdf" in mime:
            return "pdf"
        if "epub" in mime:
            return "epub"
        if "markdown" in mime or "text" in mime:
            return "txt"

    raise IngestionError(
        f"Cannot determine format for file: {file_path.name} "
        f"(extension: {ext!r})"
    )


def _disambiguate_zip(file_path: Path) -> str:
    """Distinguish DOCX from EPUB by inspecting ZIP contents."""
    import zipfile

    try:
        with zipfile.ZipFile(file_path) as zf:
            names = zf.namelist()
    except zipfile.BadZipFile:
        raise IngestionError(f"File appears to be corrupt: {file_path.name}")

    if any(n.startswith("word/") for n in names):
        return "docx"
    if "mimetype" in names or any("epub" in n for n in names):
        return "epub"
    # Default to docx for unknown ZIP-based office formats
    return "docx"
