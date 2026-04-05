"""Tests for AI generators (title, preface, acknowledgement).

All tests use the mock_ai_provider fixture — no real API calls.
"""

from pathlib import Path

import pytest

from bookforge.ai.generators import (
    generate_acknowledgement,
    generate_preface,
    generate_title,
)
from bookforge.core.models import AssembledBook, BookMetadata


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    """Create prompt files matching the real config/prompts/ templates."""
    d = tmp_path / "prompts"
    d.mkdir()

    (d / "title.txt").write_text(
        "Generate a title for: {article_titles}\nOutput only the title."
    )
    (d / "preface.txt").write_text(
        "Write a preface for {book_title} containing {article_titles}."
    )
    (d / "acknowledgement.txt").write_text(
        "Write acknowledgements for {book_title} published by {publisher_name}."
    )
    return d


@pytest.fixture
def ai_config(prompts_dir: Path) -> dict:
    return {"ai": {"prompts_dir": str(prompts_dir)}}


@pytest.fixture
def assembled() -> AssembledBook:
    return AssembledBook(
        body_html="<section class='bf-chapter'><h1>Intro</h1><p>Text.</p></section>",
        article_titles=["Machine Learning in Medicine", "Deep Learning for Imaging"],
        chapter_headings=[],
        protected_blocks=[],
        assets=[],
    )


@pytest.fixture
def metadata() -> BookMetadata:
    return BookMetadata(
        title="AI in Healthcare",
        authors=["Dr. Smith"],
        publisher_name="Academic Press",
    )


# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------


def test_generate_title(assembled, mock_ai_provider, ai_config):
    title = generate_title(assembled, mock_ai_provider, ai_config)
    # mock_ai_provider.generate returns "Mock Generated Title: Test Volume on Testing"
    assert "Mock Generated Title" in title


def test_generate_title_strips_quotes(assembled, ai_config):
    """Title generator should strip wrapping quotes."""
    from bookforge.ai.base import BaseAIProvider

    class QuotingProvider(BaseAIProvider):
        def generate(self, prompt, context, max_tokens):
            return '"A Great Book Title"'
        def rewrite(self, text, instruction, max_tokens, system_context=""):
            return text

    title = generate_title(assembled, QuotingProvider(), ai_config)
    assert title == "A Great Book Title"


# ---------------------------------------------------------------------------
# Preface
# ---------------------------------------------------------------------------


def test_generate_preface(assembled, metadata, mock_ai_provider, ai_config):
    preface = generate_preface(assembled, metadata, mock_ai_provider, ai_config)
    assert isinstance(preface, str)
    assert len(preface) > 0


# ---------------------------------------------------------------------------
# Acknowledgement
# ---------------------------------------------------------------------------


def test_generate_acknowledgement(metadata, mock_ai_provider, ai_config):
    ack = generate_acknowledgement(metadata, mock_ai_provider, ai_config)
    assert isinstance(ack, str)
    assert len(ack) > 0
