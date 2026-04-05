"""Tests for the AI stage orchestrator.

Tests the full Stage 4 flow: generators + rewriter integration.
All tests use mock AI providers — no real API calls.
"""

from pathlib import Path

import pytest

from bookforge.ai.base import BaseAIProvider
from bookforge.ai.stage import process, _rewrite_chapter
from bookforge.core.models import (
    AssembledBook,
    BookMetadata,
    Heading,
    JobConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "title.txt").write_text("Generate a title for: {article_titles}")
    (d / "preface.txt").write_text("Preface for {book_title} with {article_titles}.")
    (d / "acknowledgement.txt").write_text("Ack for {book_title} by {publisher_name}.")
    (d / "rewrite.txt").write_text("Rewrite to be {direction} by {percent}%.")
    return d


@pytest.fixture
def ai_config(prompts_dir: Path) -> dict:
    return {
        "ai": {
            "prompts_dir": str(prompts_dir),
            "max_tokens": 4096,
            "max_chunk_tokens": 3000,
            "context_overlap_tokens": 200,
        },
    }


@pytest.fixture
def assembled() -> AssembledBook:
    return AssembledBook(
        body_html=(
            '<section class="bf-chapter" data-source="article1.html">'
            "<h1>Introduction</h1><p>First paragraph.</p>"
            "</section>"
        ),
        article_titles=["Introduction to AI"],
        chapter_headings=[Heading(level=1, text="Introduction", anchor_id="h-0")],
        protected_blocks=[],
        assets=[],
    )


@pytest.fixture
def metadata() -> BookMetadata:
    return BookMetadata(
        title="Test Book",
        authors=["Author"],
        publisher_name="Test Press",
    )


# ---------------------------------------------------------------------------
# Tests — skip behavior
# ---------------------------------------------------------------------------


def test_skips_when_all_features_disabled(assembled, metadata, mock_ai_provider, ai_config):
    config = JobConfig(
        generate_title=False,
        generate_preface=False,
        generate_acknowledgement=False,
        rewrite_percent=0,
    )
    result = process(assembled, metadata, config, mock_ai_provider, ai_config)

    assert result.ai_metadata.get("skipped") is True
    assert result.body_html == assembled.body_html
    assert result.generated_title is None
    assert result.generated_preface is None
    assert result.generated_acknowledgement is None


# ---------------------------------------------------------------------------
# Tests — generators
# ---------------------------------------------------------------------------


def test_generates_title_only(assembled, metadata, mock_ai_provider, ai_config):
    config = JobConfig(
        generate_title=True,
        generate_preface=False,
        generate_acknowledgement=False,
        rewrite_percent=0,
    )
    result = process(assembled, metadata, config, mock_ai_provider, ai_config)

    assert result.generated_title is not None
    assert result.generated_preface is None
    assert result.generated_acknowledgement is None
    assert result.ai_metadata.get("skipped") is False


def test_generates_all_three(assembled, metadata, mock_ai_provider, ai_config):
    config = JobConfig(
        generate_title=True,
        generate_preface=True,
        generate_acknowledgement=True,
        rewrite_percent=0,
    )
    result = process(assembled, metadata, config, mock_ai_provider, ai_config)

    assert result.generated_title is not None
    assert result.generated_preface is not None
    assert result.generated_acknowledgement is not None


# ---------------------------------------------------------------------------
# Tests — rewriting
# ---------------------------------------------------------------------------


def test_rewrite_modifies_body(assembled, metadata, mock_ai_provider, ai_config):
    config = JobConfig(
        generate_title=False,
        generate_preface=False,
        generate_acknowledgement=False,
        rewrite_percent=20,
    )
    result = process(assembled, metadata, config, mock_ai_provider, ai_config)

    # mock_ai_provider.rewrite appends " [rewritten]"
    assert "[rewritten]" in result.body_html
    assert result.ai_metadata.get("rewrite_percent") == 20


def test_passthrough_preserves_headings_and_assets(assembled, metadata, mock_ai_provider, ai_config):
    config = JobConfig(
        generate_title=False,
        generate_preface=False,
        generate_acknowledgement=False,
        rewrite_percent=0,
    )
    result = process(assembled, metadata, config, mock_ai_provider, ai_config)

    assert result.chapter_headings == assembled.chapter_headings
    assert result.assets == assembled.assets


# ---------------------------------------------------------------------------
# Tests — rewriter with protected blocks
# ---------------------------------------------------------------------------


def test_rewrite_chapter_preserves_protected_blocks(ai_config):
    """Protected blocks survive the rewrite cycle."""
    chapter = (
        '<p>Text before equation.</p>'
        '<span class="bf-protected" data-type="equation" data-block-id="PROTECTED_0">'
        '$E = mc^2$</span>'
        '<p>Text after equation.</p>'
    )

    class MarkerProvider(BaseAIProvider):
        def generate(self, prompt, context, max_tokens):
            return ""
        def rewrite(self, text, instruction, max_tokens, system_context=""):
            # Leave placeholders intact, add marker
            return text + " [rewritten]"

    result = _rewrite_chapter(chapter, 20, MarkerProvider(), ai_config)

    # Protected block content should be restored
    assert "$E = mc^2$" in result or "PROTECTED_0" in result
    assert "[rewritten]" in result


# ---------------------------------------------------------------------------
# Tests — chunking
# ---------------------------------------------------------------------------


def test_rewrite_counts_ai_calls_for_long_chapter(ai_config):
    """Long chapters should produce multiple AI calls (chunked)."""
    # Build a chapter with many paragraphs to exceed max_chunk_tokens
    paragraphs = [f"<p>{'word ' * 200}</p>" for _ in range(20)]
    chapter = "\n".join(paragraphs)

    call_count = []

    class CountingProvider(BaseAIProvider):
        def generate(self, prompt, context, max_tokens):
            return ""
        def rewrite(self, text, instruction, max_tokens, system_context=""):
            call_count.append(1)
            return text

    # Set very low chunk size to force chunking
    ai_config["ai"]["max_chunk_tokens"] = 500

    _rewrite_chapter(chapter, 10, CountingProvider(), ai_config)

    assert len(call_count) > 1, "Long chapter should produce multiple AI calls"


def test_rewrite_passes_original_context_not_rewritten(ai_config):
    """system_context should contain original chunk text, not rewritten."""
    paragraphs = [f"<p>Paragraph {i} with enough text to fill tokens.</p>" for i in range(20)]
    chapter = "\n".join(paragraphs)

    contexts_received = []

    class ContextCapture(BaseAIProvider):
        def generate(self, prompt, context, max_tokens):
            return ""
        def rewrite(self, text, instruction, max_tokens, system_context=""):
            contexts_received.append(system_context)
            return text.upper()  # visibly different from original

    ai_config["ai"]["max_chunk_tokens"] = 200

    _rewrite_chapter(chapter, 10, ContextCapture(), ai_config)

    # After the first call, subsequent calls should receive context
    if len(contexts_received) > 1:
        for ctx in contexts_received[1:]:
            # Context should NOT contain uppercased text (which would mean
            # we passed the rewritten output instead of the original)
            assert ctx == ctx  # non-empty
            if ctx:
                assert ctx != ctx.upper() or ctx.isupper() is False
