"""Markdown ingester — Stage 1 for .md / .markdown files.

Uses Pandoc with --from gfm (GitHub-Flavored Markdown) to produce
well-formed HTML. This handles tables, fenced code blocks, and task
lists automatically. The normalizer receives HTML regardless of source format.
"""

from __future__ import annotations

from pathlib import Path

import pypandoc

from bookforge.core.exceptions import IngestionError
from bookforge.core.models import RawContent
from bookforge.core.registry import register_ingester
from bookforge.ingestion.base import BaseIngester


@register_ingester("markdown")
class MarkdownIngester(BaseIngester):
    """Converts Markdown files to HTML via Pandoc GFM mode."""

    supported_extensions = [".md", ".markdown"]
    supported_mimetypes = ["text/markdown", "text/x-markdown"]

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.supported_extensions

    def ingest(self, file_path: Path, config: dict) -> RawContent:
        try:
            html = pypandoc.convert_file(
                str(file_path),
                to="html",
                format="gfm",
                extra_args=["--standalone=false", "--wrap=none"],
            )
        except Exception as exc:
            raise IngestionError(f"Pandoc conversion failed for {file_path.name}: {exc}") from exc

        return RawContent(
            text=html,
            format_hint="html",
            assets=[],
            source_metadata={"original_format": "markdown"},
            source_path=file_path,
        )
