"""Tests for multi-file article ordering (Phase G expansion).

Tests the 3-tier ordering priority:
  1. Excel chapter_order (explicit)
  2. Excel row order (source_row_indices)
  3. Filename alphabetical sort
"""

from pathlib import Path

from bookforge.assembly.ordering import order_articles
from bookforge.core.models import BookMetadata, NormalizedContent


def _article(name: str) -> NormalizedContent:
    """Helper to create a minimal NormalizedContent with a given filename."""
    return NormalizedContent(
        body_html=f"<p>Content of {name}</p>",
        source_path=Path(name),
    )


# ---------------------------------------------------------------------------
# Priority 1: chapter_order
# ---------------------------------------------------------------------------


def test_orders_by_chapter_order():
    articles = [_article("c.html"), _article("a.html"), _article("b.html")]
    metadata = BookMetadata(
        title="Test",
        chapter_order={"b.html": 1, "a.html": 2, "c.html": 3},
    )
    result = order_articles(articles, metadata)
    assert [a.source_path.name for a in result] == ["b.html", "a.html", "c.html"]


def test_chapter_order_puts_unmapped_files_last():
    articles = [_article("c.html"), _article("a.html"), _article("b.html")]
    metadata = BookMetadata(
        title="Test",
        chapter_order={"a.html": 1},  # only a.html has explicit order
    )
    result = order_articles(articles, metadata)
    assert result[0].source_path.name == "a.html"


# ---------------------------------------------------------------------------
# Priority 2: source_row_indices (Excel row order)
# ---------------------------------------------------------------------------


def test_orders_by_row_indices():
    articles = [_article("c.html"), _article("a.html"), _article("b.html")]
    metadata = BookMetadata(
        title="Test",
        source_row_indices={"a.html": 3, "b.html": 1, "c.html": 2},
    )
    result = order_articles(articles, metadata)
    assert [a.source_path.name for a in result] == ["b.html", "c.html", "a.html"]


# ---------------------------------------------------------------------------
# Priority 3: filename alphabetical
# ---------------------------------------------------------------------------


def test_orders_alphabetically_without_metadata():
    articles = [_article("charlie.html"), _article("alpha.html"), _article("bravo.html")]
    result = order_articles(articles, None)
    assert [a.source_path.name for a in result] == [
        "alpha.html", "bravo.html", "charlie.html"
    ]


def test_orders_alphabetically_with_empty_metadata():
    articles = [_article("z.html"), _article("a.html")]
    metadata = BookMetadata(title="Test")  # no ordering fields
    result = order_articles(articles, metadata)
    assert [a.source_path.name for a in result] == ["a.html", "z.html"]


# ---------------------------------------------------------------------------
# Priority precedence
# ---------------------------------------------------------------------------


def test_chapter_order_takes_precedence_over_row_indices():
    """chapter_order should win over source_row_indices."""
    articles = [_article("a.html"), _article("b.html")]
    metadata = BookMetadata(
        title="Test",
        chapter_order={"b.html": 1, "a.html": 2},
        source_row_indices={"a.html": 1, "b.html": 2},
    )
    result = order_articles(articles, metadata)
    # chapter_order says b first
    assert [a.source_path.name for a in result] == ["b.html", "a.html"]
