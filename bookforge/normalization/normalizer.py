"""Normalizer — Stage 2 of the pipeline.

Converts RawContent (any format) into NormalizedContent (clean semantic HTML
with bf-protected tags). All downstream stages consume NormalizedContent.

Processing order (sequential — each step feeds the next):
  1. html_cleaner      — strip non-semantic tags and attributes
  2. structure_detector — wrap in <article>, detect headings + title
  3. equation_detector  — tag LaTeX/MathML as bf-protected
  4. table_standardizer — normalise + tag tables as bf-protected
"""

from __future__ import annotations

from pathlib import Path

from bookforge.core.exceptions import NormalizationError
from bookforge.core.models import NormalizedContent, RawContent
from bookforge.normalization.html_cleaner import clean_html
from bookforge.normalization.equation_detector import detect_equations
from bookforge.normalization.structure_detector import detect_structure
from bookforge.normalization.table_standardizer import standardize_tables


class Normalizer:
    """Converts RawContent to NormalizedContent."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}

    def normalize(self, raw: RawContent) -> NormalizedContent:
        """Run the full normalization pipeline on a single RawContent."""
        try:
            return self._run(raw)
        except NormalizationError:
            raise
        except Exception as exc:
            raise NormalizationError(
                f"Normalization failed for {raw.source_path.name}: {exc}"
            ) from exc

    def _run(self, raw: RawContent) -> NormalizedContent:
        html = raw.text

        # Step 1: clean
        html = clean_html(html)

        # Step 2: detect structure
        html, detected_title, headings = detect_structure(html, raw.source_path)

        # Steps 3+4 share a block counter so IDs are globally unique
        # within this article (cross-article uniqueness is handled in Assembly)
        block_counter = 0

        # Step 3: detect equations
        html, equation_blocks, block_counter = detect_equations(html, block_counter)

        # Step 4: standardize tables
        html, table_blocks, block_counter = standardize_tables(html, block_counter)

        all_blocks = equation_blocks + table_blocks

        return NormalizedContent(
            body_html=html,
            detected_title=detected_title,
            detected_headings=headings,
            protected_blocks=all_blocks,
            assets=raw.assets,
            source_metadata=raw.source_metadata,
            source_path=raw.source_path,
        )
