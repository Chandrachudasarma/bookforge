"""Tests for the OCR ingester (Stage 1).

Mocks the OCR engine to avoid requiring Tesseract in the test environment.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bookforge.core.models import RawContent
from bookforge.ingestion.ocr_ingester import OcrIngester


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ocr_config() -> dict:
    return {
        "ocr": {
            "engine": "tesseract",
            "language": "eng",
            "page_segmentation_mode": 6,
        },
    }


@pytest.fixture
def fake_image(tmp_path: Path) -> Path:
    """Create a minimal PNG file (1x1 pixel)."""
    # Minimal valid PNG: 8-byte signature + IHDR + IDAT + IEND
    import struct
    import zlib

    def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        return struct.pack(">I", len(data)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr = _png_chunk(b"IHDR", ihdr_data)
    raw_data = b"\x00\x00\x00\x00"  # filter byte + 1 pixel RGB
    idat = _png_chunk(b"IDAT", zlib.compress(raw_data))
    iend = _png_chunk(b"IEND", b"")

    path = tmp_path / "scan.png"
    path.write_bytes(signature + ihdr + idat + iend)
    return path


@pytest.fixture
def fake_tiff(tmp_path: Path) -> Path:
    path = tmp_path / "scan.tiff"
    path.write_bytes(b"fake tiff content")
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ocr_ingests_image(fake_image, ocr_config, monkeypatch):
    """OCR ingester produces HTML from image OCR text."""
    monkeypatch.setattr(
        "bookforge.ingestion.ocr_ingester.get_ocr_engine",
        lambda name: _make_fake_engine("Line one.\n\nLine two."),
    )

    ingester = OcrIngester()
    raw = ingester.ingest(fake_image, ocr_config)

    assert raw.format_hint == "html"
    assert "<p>" in raw.text
    assert "Line one" in raw.text
    assert "Line two" in raw.text


def test_ocr_passes_psm_to_engine(fake_image, ocr_config, monkeypatch):
    """Verify psm from config is forwarded to the OCR engine."""
    received_kwargs = {}

    class SpyEngine:
        def ocr_image(self, image_path, language="eng", **kwargs):
            received_kwargs.update(kwargs)
            return "text"

    monkeypatch.setattr(
        "bookforge.ingestion.ocr_ingester.get_ocr_engine",
        lambda name: SpyEngine(),
    )

    ingester = OcrIngester()
    ingester.ingest(fake_image, ocr_config)

    assert received_kwargs.get("psm") == 6


def test_ocr_escapes_html_entities(fake_image, ocr_config, monkeypatch):
    """Angle brackets and ampersands in OCR text are escaped."""
    monkeypatch.setattr(
        "bookforge.ingestion.ocr_ingester.get_ocr_engine",
        lambda name: _make_fake_engine("x < y & z > w"),
    )

    ingester = OcrIngester()
    raw = ingester.ingest(fake_image, ocr_config)

    assert "&lt;" in raw.text
    assert "&amp;" in raw.text
    assert "&gt;" in raw.text


def test_can_handle_image_formats():
    ingester = OcrIngester()
    assert ingester.can_handle(Path("scan.tiff"))
    assert ingester.can_handle(Path("scan.tif"))
    assert ingester.can_handle(Path("scan.png"))
    assert ingester.can_handle(Path("scan.jpg"))
    assert ingester.can_handle(Path("scan.jpeg"))
    assert ingester.can_handle(Path("scan.bmp"))
    assert not ingester.can_handle(Path("doc.pdf"))
    assert not ingester.can_handle(Path("doc.html"))


def test_ocr_empty_text_produces_empty_paragraph(fake_image, ocr_config, monkeypatch):
    monkeypatch.setattr(
        "bookforge.ingestion.ocr_ingester.get_ocr_engine",
        lambda name: _make_fake_engine(""),
    )

    ingester = OcrIngester()
    raw = ingester.ingest(fake_image, ocr_config)

    assert raw.format_hint == "html"
    assert "<p>" in raw.text  # fallback empty paragraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_engine(text: str):
    """Create a fake OCR engine that returns the given text."""

    class FakeEngine:
        def ocr_image(self, image_path, language="eng", **kwargs):
            return text

    return FakeEngine()
