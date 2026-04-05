"""Tests for the PDF ingester (Stage 1).

Creates real PDF files via PyMuPDF (fitz) for testing.
Tests digital path (text extraction) and scanned detection heuristic.
OCR path is tested separately in test_ocr_ingester.py.
"""

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz", reason="PyMuPDF not installed")

from bookforge.ingestion.pdf_ingester import PdfIngester, _detect_pdf_type


# ---------------------------------------------------------------------------
# Fixtures — create real PDF files
# ---------------------------------------------------------------------------


@pytest.fixture
def digital_pdf(tmp_path: Path) -> Path:
    """PDF with real text content (digital, not scanned)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4

    # Insert enough text to exceed the scanned threshold (100 chars/page)
    text = (
        "Introduction to Testing\n\n"
        "This is a digital PDF with enough text content to be classified "
        "as a digital document by the detection heuristic. The average "
        "characters per page should exceed one hundred characters."
    )
    page.insert_text((72, 72), text, fontsize=12)

    path = tmp_path / "digital.pdf"
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def scanned_pdf(tmp_path: Path) -> Path:
    """PDF with minimal/no text (simulates a scanned document)."""
    doc = fitz.open()
    # Empty page — no text at all
    doc.new_page(width=595, height=842)
    doc.new_page(width=595, height=842)

    path = tmp_path / "scanned.pdf"
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def pdf_config(tmp_path: Path) -> dict:
    return {
        "pipeline": {"temp_dir": str(tmp_path / "temp")},
        "ocr": {"engine": "tesseract", "language": "eng", "dpi": 150},
    }


# ---------------------------------------------------------------------------
# Tests — detection heuristic
# ---------------------------------------------------------------------------


def test_detect_digital_pdf(digital_pdf):
    assert _detect_pdf_type(digital_pdf) == "digital"


def test_detect_scanned_pdf(scanned_pdf):
    assert _detect_pdf_type(scanned_pdf) == "scanned"


# ---------------------------------------------------------------------------
# Tests — digital ingestion
# ---------------------------------------------------------------------------


def test_ingests_digital_pdf(digital_pdf, pdf_config):
    ingester = PdfIngester()
    raw = ingester.ingest(digital_pdf, pdf_config)

    assert raw.format_hint == "html"
    assert raw.source_path == digital_pdf
    assert raw.source_metadata.get("pdf_type") == "digital"
    # Should contain the text we inserted
    assert "Testing" in raw.text or "digital" in raw.text


def test_digital_pdf_wraps_pages_in_divs(digital_pdf, pdf_config):
    ingester = PdfIngester()
    raw = ingester.ingest(digital_pdf, pdf_config)

    assert "pdf-page" in raw.text
    assert "data-page" in raw.text


def test_can_handle_returns_true_for_pdf():
    ingester = PdfIngester()
    assert ingester.can_handle(Path("document.pdf"))
    assert not ingester.can_handle(Path("document.docx"))


# ---------------------------------------------------------------------------
# Tests — scanned PDF routes to OCR
# ---------------------------------------------------------------------------


def test_scanned_pdf_calls_ocr_engine(scanned_pdf, pdf_config, monkeypatch):
    """Verify scanned PDF delegates to OCR engine (mocked)."""
    from bookforge.ingestion.ocr.base import PageResult

    ocr_called = []

    class FakeOCREngine:
        def ocr_pdf(self, pdf_path, language="eng", **kwargs):
            ocr_called.append(pdf_path)
            return [PageResult(page_num=0, text="OCR scanned text")]

    monkeypatch.setattr(
        "bookforge.ingestion.pdf_ingester.get_ocr_engine",
        lambda name: FakeOCREngine(),
    )

    ingester = PdfIngester()
    raw = ingester.ingest(scanned_pdf, pdf_config)

    assert len(ocr_called) == 1
    assert raw.source_metadata.get("pdf_type") == "scanned"
    assert "OCR scanned text" in raw.text
