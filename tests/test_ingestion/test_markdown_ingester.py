"""Tests for the Markdown ingester (Stage 1).

Requires pandoc to be installed on the system (pypandoc wraps the CLI).
"""

from pathlib import Path
import shutil

import pytest

pypandoc = pytest.importorskip("pypandoc", reason="pypandoc not installed")

_HAS_PANDOC = shutil.which("pandoc") is not None
pytestmark = pytest.mark.skipif(not _HAS_PANDOC, reason="pandoc binary not installed")

from bookforge.ingestion.markdown_ingester import MarkdownIngester


def test_ingests_simple_markdown(sample_markdown_file, pipeline_config):
    ingester = MarkdownIngester()
    raw = ingester.ingest(sample_markdown_file, pipeline_config)

    assert raw.format_hint == "html"
    # Pandoc GFM produces HTML headings from # syntax
    assert "<h1" in raw.text or "Test Chapter" in raw.text
    assert raw.source_path == sample_markdown_file


def test_preserves_bold_and_italic(tmp_path, pipeline_config):
    content = "# Title\n\nSome **bold** and *italic* text.\n"
    path = tmp_path / "styled.md"
    path.write_text(content, encoding="utf-8")

    ingester = MarkdownIngester()
    raw = ingester.ingest(path, pipeline_config)

    assert "<strong>" in raw.text or "<b>" in raw.text
    assert "<em>" in raw.text or "<i>" in raw.text


def test_converts_gfm_table(tmp_path, pipeline_config):
    content = """# Data

| Name  | Value |
|-------|-------|
| Alpha | 1     |
| Beta  | 2     |
"""
    path = tmp_path / "table.md"
    path.write_text(content, encoding="utf-8")

    ingester = MarkdownIngester()
    raw = ingester.ingest(path, pipeline_config)

    assert "<table" in raw.text
    assert "Alpha" in raw.text
    assert "Beta" in raw.text


def test_can_handle_returns_true_for_md():
    ingester = MarkdownIngester()
    assert ingester.can_handle(Path("readme.md"))
    assert ingester.can_handle(Path("doc.markdown"))
    assert not ingester.can_handle(Path("doc.txt"))


def test_returns_no_assets(sample_markdown_file, pipeline_config):
    ingester = MarkdownIngester()
    raw = ingester.ingest(sample_markdown_file, pipeline_config)
    assert raw.assets == []


def test_source_metadata_records_format(sample_markdown_file, pipeline_config):
    ingester = MarkdownIngester()
    raw = ingester.ingest(sample_markdown_file, pipeline_config)
    assert raw.source_metadata.get("original_format") == "markdown"
