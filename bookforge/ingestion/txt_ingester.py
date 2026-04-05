"""Plain text ingester — Stage 1 for .txt files.

Applies heuristic structure detection to produce basic HTML before
normalization. If no structure is detected, the entire text becomes
a single chapter with paragraph breaks only.

Heuristic detection order:
1. Lines matching Chapter N / CHAPTER ONE / Chapter IV patterns → <h1>
2. ALL-CAPS lines (≥4 words, ≤10 words) → <h2>
3. Separator lines (---, ***, ===) → section break
4. Blank-line-delimited groups → <p>
"""

from __future__ import annotations

import re
from pathlib import Path

import chardet

from bookforge.core.exceptions import IngestionError
from bookforge.core.models import RawContent
from bookforge.core.registry import register_ingester
from bookforge.ingestion.base import BaseIngester

# Chapter heading patterns
_CHAPTER_PATTERNS = [
    re.compile(r"^chapter\s+(\d+|[ivxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten)[\s.:–-]?(.*)$", re.IGNORECASE),
    re.compile(r"^(part|section|unit)\s+(\d+|[ivxlcdm]+)[\s.:–-]?(.*)$", re.IGNORECASE),
]

# Separator lines that indicate section breaks
_SEPARATOR = re.compile(r"^[-*=]{3,}\s*$")

# ALL-CAPS heading: 4–10 words, no digits-only content
_ALL_CAPS = re.compile(r"^[A-Z][A-Z\s\-,:]{10,60}[A-Z]$")


@register_ingester("txt")
class TxtIngester(BaseIngester):
    """Converts plain text files to structured HTML."""

    supported_extensions = [".txt", ".text"]
    supported_mimetypes = ["text/plain"]

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.supported_extensions

    def ingest(self, file_path: Path, config: dict) -> RawContent:
        try:
            raw_bytes = file_path.read_bytes()
        except OSError as exc:
            raise IngestionError(f"Cannot read file: {file_path}") from exc

        encoding = _detect_encoding(raw_bytes)
        text = raw_bytes.decode(encoding, errors="replace")

        html = _text_to_html(text)

        return RawContent(
            text=html,
            format_hint="html",
            assets=[],
            source_metadata={"encoding": encoding, "original_format": "txt"},
            source_path=file_path,
        )


# ---------------------------------------------------------------------------
# Text → HTML conversion
# ---------------------------------------------------------------------------


def _text_to_html(text: str) -> str:
    """Convert plain text to basic semantic HTML."""
    lines = text.splitlines()
    blocks: list[str] = []
    para_lines: list[str] = []

    def flush_para():
        if para_lines:
            content = " ".join(l.strip() for l in para_lines if l.strip())
            if content:
                blocks.append(f"<p>{_escape(content)}</p>")
            para_lines.clear()

    for line in lines:
        stripped = line.strip()

        if not stripped:
            flush_para()
            continue

        # Chapter heading
        heading = _detect_chapter_heading(stripped)
        if heading:
            flush_para()
            blocks.append(heading)
            continue

        # ALL-CAPS heading
        if _ALL_CAPS.match(stripped):
            word_count = len(stripped.split())
            if 4 <= word_count <= 10:
                flush_para()
                blocks.append(f"<h2>{_escape(stripped.title())}</h2>")
                continue

        # Separator line
        if _SEPARATOR.match(stripped):
            flush_para()
            continue

        para_lines.append(stripped)

    flush_para()
    return "\n".join(blocks)


def _detect_chapter_heading(line: str) -> str | None:
    """Return an <h1> tag if the line looks like a chapter heading."""
    for pattern in _CHAPTER_PATTERNS:
        m = pattern.match(line)
        if m:
            full_text = line.strip()
            return f"<h1>{_escape(full_text)}</h1>"
    return None


def _escape(text: str) -> str:
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _detect_encoding(raw_bytes: bytes) -> str:
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    result = chardet.detect(raw_bytes[:4096])
    return result.get("encoding") or "utf-8"
