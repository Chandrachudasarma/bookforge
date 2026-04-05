"""Tests for the EPUB ingester (Stage 1).

Creates real EPUB files via ebooklib for testing.
"""

from pathlib import Path
from uuid import uuid4

import pytest

ebooklib = pytest.importorskip("ebooklib", reason="ebooklib not installed")
from ebooklib import epub

from bookforge.ingestion.epub_ingester import EpubIngester


# ---------------------------------------------------------------------------
# Fixtures — create real EPUB files
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_epub(tmp_path: Path) -> Path:
    """Minimal valid EPUB with one chapter."""
    book = epub.EpubBook()
    book.set_identifier(str(uuid4()))
    book.set_title("Test EPUB")
    book.set_language("en")
    book.add_author("Test Author")

    # Add a chapter
    ch1 = epub.EpubHtml(
        title="Chapter 1",
        file_name="chapter_1.xhtml",
        content=(
            "<html><body>"
            "<h1>Chapter One</h1>"
            "<p>First paragraph of chapter one.</p>"
            "<p>Second paragraph with <em>emphasis</em>.</p>"
            "</body></html>"
        ),
    )
    book.add_item(ch1)

    # Spine and TOC
    book.spine = ["nav", ch1]
    book.toc = [epub.Link("chapter_1.xhtml", "Chapter 1", "ch1")]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    path = tmp_path / "test.epub"
    epub.write_epub(str(path), book)
    return path


@pytest.fixture
def multi_chapter_epub(tmp_path: Path) -> Path:
    """EPUB with two chapters."""
    book = epub.EpubBook()
    book.set_identifier(str(uuid4()))
    book.set_title("Multi Chapter EPUB")
    book.set_language("en")
    book.add_author("Author Two")

    ch1 = epub.EpubHtml(
        title="Intro",
        file_name="intro.xhtml",
        content="<html><body><h1>Introduction</h1><p>Intro text.</p></body></html>",
    )
    ch2 = epub.EpubHtml(
        title="Methods",
        file_name="methods.xhtml",
        content="<html><body><h1>Methods</h1><p>Methods text.</p></body></html>",
    )
    book.add_item(ch1)
    book.add_item(ch2)
    book.spine = ["nav", ch1, ch2]
    book.toc = [
        epub.Link("intro.xhtml", "Introduction", "intro"),
        epub.Link("methods.xhtml", "Methods", "methods"),
    ]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    path = tmp_path / "multi.epub"
    epub.write_epub(str(path), book)
    return path


@pytest.fixture
def epub_config(tmp_path: Path) -> dict:
    return {
        "pipeline": {"temp_dir": str(tmp_path / "temp")},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ingests_simple_epub(simple_epub, epub_config):
    ingester = EpubIngester()
    raw = ingester.ingest(simple_epub, epub_config)

    assert raw.format_hint == "html"
    assert raw.source_path == simple_epub
    assert raw.source_metadata.get("original_format") == "epub"


def test_extracts_chapter_content(simple_epub, epub_config):
    ingester = EpubIngester()
    raw = ingester.ingest(simple_epub, epub_config)

    assert "Chapter One" in raw.text
    assert "First paragraph" in raw.text


def test_extracts_title_metadata(simple_epub, epub_config):
    ingester = EpubIngester()
    raw = ingester.ingest(simple_epub, epub_config)

    assert raw.source_metadata.get("title") == "Test EPUB"


def test_multi_chapter_extracts_all_content(multi_chapter_epub, epub_config):
    ingester = EpubIngester()
    raw = ingester.ingest(multi_chapter_epub, epub_config)

    assert "Introduction" in raw.text
    assert "Methods" in raw.text


def test_can_handle_returns_true_for_epub():
    ingester = EpubIngester()
    assert ingester.can_handle(Path("book.epub"))
    assert not ingester.can_handle(Path("book.pdf"))
    assert not ingester.can_handle(Path("book.docx"))
