"""Tests for the TXT ingester (Stage 1).

Covers all 5 heuristic detection rules:
  1. Chapter N patterns → <h1>
  2. ALL-CAPS headings → <h2>
  3. Separator lines (---, ***, ===)
  4. Blank-line paragraphs → <p>
  5. Encoding detection
"""

from pathlib import Path

from bookforge.ingestion.txt_ingester import TxtIngester


def test_ingests_simple_txt(sample_txt_file, pipeline_config):
    ingester = TxtIngester()
    raw = ingester.ingest(sample_txt_file, pipeline_config)

    assert raw.format_hint == "html"
    assert raw.source_path == sample_txt_file


def test_detects_chapter_heading_pattern(tmp_path, pipeline_config):
    content = "Chapter 1: Introduction\n\nFirst paragraph.\n"
    path = tmp_path / "chapters.txt"
    path.write_text(content, encoding="utf-8")

    ingester = TxtIngester()
    raw = ingester.ingest(path, pipeline_config)

    assert "<h1>" in raw.text
    assert "Chapter 1: Introduction" in raw.text


def test_detects_roman_numeral_chapter(tmp_path, pipeline_config):
    content = "Chapter IV\n\nContent of chapter four.\n"
    path = tmp_path / "roman.txt"
    path.write_text(content, encoding="utf-8")

    ingester = TxtIngester()
    raw = ingester.ingest(path, pipeline_config)

    assert "<h1>" in raw.text


def test_detects_all_caps_heading(tmp_path, pipeline_config):
    content = "METHODS AND MATERIALS USED HERE\n\nSome paragraph text.\n"
    path = tmp_path / "caps.txt"
    path.write_text(content, encoding="utf-8")

    ingester = TxtIngester()
    raw = ingester.ingest(path, pipeline_config)

    assert "<h2>" in raw.text


def test_wraps_paragraphs_in_p_tags(tmp_path, pipeline_config):
    content = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n"
    path = tmp_path / "paras.txt"
    path.write_text(content, encoding="utf-8")

    ingester = TxtIngester()
    raw = ingester.ingest(path, pipeline_config)

    assert raw.text.count("<p>") == 3


def test_separator_lines_create_section_breaks(tmp_path, pipeline_config):
    content = "First section.\n\n---\n\nSecond section.\n"
    path = tmp_path / "seps.txt"
    path.write_text(content, encoding="utf-8")

    ingester = TxtIngester()
    raw = ingester.ingest(path, pipeline_config)

    # Separator itself should not appear in output as text
    assert "---" not in raw.text
    # But both sections should be present
    assert "First section" in raw.text
    assert "Second section" in raw.text


def test_handles_utf8_encoding(tmp_path, pipeline_config):
    content = "Chapter 1: Résumé\n\nCafé naïve coöperate.\n"
    path = tmp_path / "utf8.txt"
    path.write_text(content, encoding="utf-8")

    ingester = TxtIngester()
    raw = ingester.ingest(path, pipeline_config)

    assert "Caf" in raw.text  # content preserved


def test_handles_latin1_encoding(tmp_path, pipeline_config):
    content = "Chapter 1: Über\n\nStraße und Grüße.\n"
    path = tmp_path / "latin1.txt"
    path.write_bytes(content.encode("latin-1"))

    ingester = TxtIngester()
    raw = ingester.ingest(path, pipeline_config)

    # Should decode without crashing
    assert raw.format_hint == "html"


def test_can_handle_returns_true_for_txt():
    ingester = TxtIngester()
    assert ingester.can_handle(Path("doc.txt"))
    assert ingester.can_handle(Path("doc.text"))
    assert not ingester.can_handle(Path("doc.md"))


def test_escapes_html_in_content(tmp_path, pipeline_config):
    content = "The formula x < y & z > w.\n"
    path = tmp_path / "escape.txt"
    path.write_text(content, encoding="utf-8")

    ingester = TxtIngester()
    raw = ingester.ingest(path, pipeline_config)

    assert "&lt;" in raw.text
    assert "&amp;" in raw.text
    assert "&gt;" in raw.text
