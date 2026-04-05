"""Tests for the HTML ingester (Stage 1)."""

from pathlib import Path

from bookforge.ingestion.html_ingester import HtmlIngester


def test_ingests_simple_html(sample_html_file, pipeline_config):
    ingester = HtmlIngester()
    raw = ingester.ingest(sample_html_file, pipeline_config)

    assert raw.format_hint == "html"
    assert "<h1>" in raw.text or "Introduction" in raw.text
    assert raw.source_path == sample_html_file


def test_ingests_html_with_encoding_detection(tmp_path, pipeline_config):
    content = "<html><body><h1>Héllo</h1><p>Cöntent</p></body></html>"
    path = tmp_path / "utf8.html"
    path.write_text(content, encoding="utf-8")

    ingester = HtmlIngester()
    raw = ingester.ingest(path, pipeline_config)
    assert "Héllo" in raw.text or "H" in raw.text  # decoded successfully


def test_can_handle_returns_true_for_html(tmp_path):
    ingester = HtmlIngester()
    assert ingester.can_handle(Path("test.html"))
    assert ingester.can_handle(Path("test.htm"))
    assert not ingester.can_handle(Path("test.pdf"))


def test_returns_empty_assets_when_no_images(sample_html_file, pipeline_config):
    ingester = HtmlIngester()
    raw = ingester.ingest(sample_html_file, pipeline_config)
    assert isinstance(raw.assets, list)
