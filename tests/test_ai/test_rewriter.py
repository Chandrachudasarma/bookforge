"""Tests for the rewriter module — chunking and token counting.

Extract/restore tests already exist in test_normalization/test_protected_blocks.py.
These tests focus on the chunking logic.
"""

from bookforge.ai.rewriter import count_tokens, split_at_paragraphs


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------


def test_count_tokens_returns_positive_int():
    result = count_tokens("Hello, world!")
    assert isinstance(result, int)
    assert result > 0


def test_count_tokens_longer_text_has_more_tokens():
    short = count_tokens("Hello")
    long = count_tokens("Hello " * 100)
    assert long > short


# ---------------------------------------------------------------------------
# Paragraph splitting
# ---------------------------------------------------------------------------


def test_split_single_paragraph_under_limit():
    html = "<p>Short paragraph.</p>"
    chunks = split_at_paragraphs(html, max_tokens=1000)
    assert len(chunks) == 1
    assert "Short paragraph" in chunks[0]


def test_split_multiple_paragraphs_under_limit():
    html = "<p>First.</p><p>Second.</p><p>Third.</p>"
    chunks = split_at_paragraphs(html, max_tokens=5000)
    assert len(chunks) == 1  # all fit in one chunk


def test_split_forces_multiple_chunks():
    # Create paragraphs that together exceed the limit
    paragraphs = [f"<p>{'word ' * 100}</p>" for _ in range(10)]
    html = "\n".join(paragraphs)

    chunks = split_at_paragraphs(html, max_tokens=200)
    assert len(chunks) > 1


def test_split_never_splits_mid_paragraph():
    paragraphs = [f"<p>Paragraph {i} with some text content here.</p>" for i in range(5)]
    html = "\n".join(paragraphs)

    chunks = split_at_paragraphs(html, max_tokens=50)

    for chunk in chunks:
        # Each chunk should have complete <p>...</p> tags
        assert chunk.count("<p>") == chunk.count("</p>")


def test_split_plain_text_fallback():
    # No <p> tags — should fall back to line-based splitting
    text = "\n".join([f"Line {i} " + "word " * 50 for i in range(10)])
    chunks = split_at_paragraphs(text, max_tokens=100)
    assert len(chunks) >= 1
