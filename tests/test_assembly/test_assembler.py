"""Tests for Stage 3 Assembler."""

from pathlib import Path

from bookforge.assembly.assembler import assemble
from bookforge.core.models import BookMetadata, NormalizedContent


def _make_article(title: str, content: str, source: str = "article.html") -> NormalizedContent:
    return NormalizedContent(
        body_html=f"<article><h1>{title}</h1><p>{content}</p></article>",
        detected_title=title,
        source_path=Path(source),
    )


def test_assemble_single_article():
    article = _make_article("Introduction", "First chapter content.")
    book = assemble([article])

    assert "Introduction" in book.body_html
    assert "First chapter content." in book.body_html
    assert book.article_titles == ["Introduction"]


def test_assemble_multiple_articles_preserves_order():
    a1 = _make_article("Chapter One", "Content one.", "ch1.html")
    a2 = _make_article("Chapter Two", "Content two.", "ch2.html")
    book = assemble([a1, a2])

    assert book.article_titles == ["Chapter One", "Chapter Two"]
    pos_one = book.body_html.index("Content one.")
    pos_two = book.body_html.index("Content two.")
    assert pos_one < pos_two


def test_protected_blocks_renumbered_across_articles():
    from bookforge.core.models import ProtectedBlock, ProtectedBlockType
    block = ProtectedBlock(
        block_id="PROTECTED_0",
        block_type=ProtectedBlockType.EQUATION,
        original_html="$x$",
        source_format="latex_inline",
    )
    a1 = NormalizedContent(
        body_html='<p><span class="bf-protected" data-block-id="PROTECTED_0">$x$</span></p>',
        detected_title="A1",
        protected_blocks=[block],
        source_path=Path("a1.html"),
    )
    a2 = NormalizedContent(
        body_html='<p><span class="bf-protected" data-block-id="PROTECTED_0">$y$</span></p>',
        detected_title="A2",
        protected_blocks=[
            ProtectedBlock(
                block_id="PROTECTED_0",
                block_type=ProtectedBlockType.EQUATION,
                original_html="$y$",
                source_format="latex_inline",
            )
        ],
        source_path=Path("a2.html"),
    )

    book = assemble([a1, a2])

    # After assembly, IDs must be globally unique
    ids = [b.block_id for b in book.protected_blocks]
    assert len(ids) == len(set(ids)), "Protected block IDs must be globally unique"


def test_assemble_raises_on_empty_input():
    from bookforge.core.exceptions import AssemblyError
    import pytest
    with pytest.raises(AssemblyError):
        assemble([])
