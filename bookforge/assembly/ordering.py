"""Article ordering logic for Stage 3 (Assemble).

Priority order (per ARCHITECTURE §3 Stage 3):
1. Excel chapter_order column  — explicit integer ordering
2. Excel row order             — positional in sheet (most common)
3. Filename alphabetical sort  — single-upload without Excel
"""

from __future__ import annotations

from pathlib import Path

from bookforge.core.models import BookMetadata, NormalizedContent


def order_articles(
    articles: list[NormalizedContent],
    metadata: BookMetadata | None,
) -> list[NormalizedContent]:
    """Return articles in the correct chapter order."""
    if not metadata:
        return sorted(articles, key=lambda a: a.source_path.name)

    if metadata.chapter_order:
        return sorted(
            articles,
            key=lambda a: metadata.chapter_order.get(a.source_path.name, 9999),
        )

    if metadata.source_row_indices:
        return sorted(
            articles,
            key=lambda a: metadata.source_row_indices.get(a.source_path.name, 9999),
        )

    return sorted(articles, key=lambda a: a.source_path.name)
