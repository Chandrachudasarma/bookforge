"""Shared test fixtures for BookForge.

Provides:
  - tmp_dir: temporary directory per test
  - sample_html_file: a simple HTML file for pipeline tests
  - sample_metadata: minimal BookMetadata
  - sample_job_config: minimal JobConfig
  - mock_ai_provider: deterministic AI provider that never calls the API
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bookforge.core.models import BookMetadata, JobConfig


# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """Temporary directory (pytest built-in, aliased for clarity)."""
    return tmp_path


# ---------------------------------------------------------------------------
# Sample files
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_html_file(tmp_path: Path) -> Path:
    """Simple HTML file with a heading, paragraph, and table."""
    content = """<!DOCTYPE html>
<html>
<head><title>Test Chapter</title></head>
<body>
<h1>Introduction</h1>
<p>This is the first paragraph of the test chapter.</p>
<p>The formula $E = mc^2$ is one of the most famous equations in physics.</p>
<h2>Background</h2>
<p>More content here.</p>
<table>
  <thead><tr><th>Name</th><th>Value</th></tr></thead>
  <tbody>
    <tr><td>Alpha</td><td>1.0</td></tr>
    <tr><td>Beta</td><td>2.0</td></tr>
  </tbody>
</table>
</body>
</html>"""
    path = tmp_path / "test_chapter.html"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def sample_markdown_file(tmp_path: Path) -> Path:
    """Simple Markdown file with GFM features."""
    content = """# Test Chapter

This is the opening paragraph.

## Section One

Some content with **bold** and *italic* text.

| Col A | Col B |
|-------|-------|
| 1     | 2     |
| 3     | 4     |
"""
    path = tmp_path / "test_chapter.md"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def sample_txt_file(tmp_path: Path) -> Path:
    """Plain text file with chapter headings."""
    content = """Chapter 1: Introduction

This is the first paragraph of the introduction chapter.

It continues here with more text.

Chapter 2: Methods

This chapter describes the methods used.

More detail about the methodology.
"""
    path = tmp_path / "test_chapter.txt"
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Metadata and config
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_metadata() -> BookMetadata:
    return BookMetadata(
        title="Test Book: A Sample Volume",
        authors=["Jane Smith"],
        publisher_name="Test Publisher",
        year=2026,
        language="en",
    )


@pytest.fixture
def sample_job_config() -> JobConfig:
    return JobConfig(
        template="academic",
        rewrite_percent=0,
        generate_title=False,
        generate_preface=False,
        generate_acknowledgement=False,
        output_formats=["epub"],
    )


@pytest.fixture
def pipeline_config(tmp_path: Path) -> dict:
    """Config dict with temp_dir set to the test's tmp directory."""
    return {
        "pipeline": {
            "temp_dir": str(tmp_path / "temp"),
            "max_concurrent_files": 1,
        },
        "ocr": {
            "engine": "tesseract",
            "language": "eng",
            "page_segmentation_mode": 6,
        },
    }


# ---------------------------------------------------------------------------
# Mock AI provider
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ai_provider():
    """Deterministic AI provider — never calls any external API."""
    from bookforge.ai.base import BaseAIProvider

    class MockAIProvider(BaseAIProvider):
        def generate(self, prompt: str, context: str, max_tokens: int) -> str:
            return "Mock Generated Title: Test Volume on Testing"

        def rewrite(
            self, text: str, instruction: str, max_tokens: int, system_context: str = ""
        ) -> str:
            # Return text with a marker to prove it was processed
            return text.strip() + " [rewritten]"

    return MockAIProvider()
