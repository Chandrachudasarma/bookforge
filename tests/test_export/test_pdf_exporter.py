"""Tests for the PDF exporter (Stage 6).

WeasyPrint is required (plus pango system library). Tests skip if not available.
"""

from pathlib import Path

import pytest

try:
    import weasyprint  # noqa: F401
    _HAS_WEASYPRINT = True
except (ImportError, OSError):
    _HAS_WEASYPRINT = False

pytestmark = pytest.mark.skipif(not _HAS_WEASYPRINT, reason="weasyprint not available (missing pango?)")

from bookforge.core.models import (
    BookManifest,
    BookMetadata,
    BookSection,
    SectionRole,
)
from bookforge.export.pdf_exporter import PdfExporter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def basic_manifest() -> BookManifest:
    return BookManifest(
        sections=[
            BookSection(
                role=SectionRole.CHAPTER,
                title="Introduction",
                content_html="<h1>Introduction</h1><p>First paragraph of the chapter.</p>",
                order=1,
            ),
        ],
        metadata=BookMetadata(title="Test PDF Book", authors=["Author One"], language="en"),
        assets=[],
    )


@pytest.fixture
def manifest_with_table() -> BookManifest:
    table_html = (
        "<h1>Results</h1>"
        "<table>"
        "<thead><tr><th>Metric</th><th>Score</th></tr></thead>"
        "<tbody>"
        "<tr><td>Accuracy</td><td>0.95</td></tr>"
        "<tr><td>Recall</td><td>0.90</td></tr>"
        "</tbody>"
        "</table>"
    )
    return BookManifest(
        sections=[
            BookSection(
                role=SectionRole.CHAPTER,
                title="Results",
                content_html=table_html,
                order=1,
            ),
        ],
        metadata=BookMetadata(title="Table PDF", authors=["Author"]),
        assets=[],
    )


@pytest.fixture
def manifest_with_equation() -> BookManifest:
    eq_html = (
        "<h1>Physics</h1>"
        '<p>The equation <span class="bf-protected" data-type="equation" '
        'data-block-id="PROTECTED_0">$E = mc^2$</span> is famous.</p>'
    )
    return BookManifest(
        sections=[
            BookSection(
                role=SectionRole.CHAPTER,
                title="Physics",
                content_html=eq_html,
                order=1,
            ),
        ],
        metadata=BookMetadata(title="Equation PDF", authors=["Physicist"]),
        assets=[],
    )


# ---------------------------------------------------------------------------
# Tests — basic export
# ---------------------------------------------------------------------------


def test_exports_valid_pdf(basic_manifest, tmp_path):
    exporter = PdfExporter()
    out = tmp_path / "output.pdf"
    result = exporter.export(basic_manifest, template=None, output_path=out)

    assert result.success
    assert out.exists()
    assert out.stat().st_size > 0


def test_pdf_is_valid_file(basic_manifest, tmp_path):
    """Verify the output starts with PDF magic bytes."""
    exporter = PdfExporter()
    out = tmp_path / "output.pdf"
    exporter.export(basic_manifest, template=None, output_path=out)

    header = out.read_bytes()[:5]
    assert header == b"%PDF-"


# ---------------------------------------------------------------------------
# Tests — table rendering
# ---------------------------------------------------------------------------


def test_pdf_with_table_exports(manifest_with_table, tmp_path):
    exporter = PdfExporter()
    out = tmp_path / "output.pdf"
    result = exporter.export(manifest_with_table, template=None, output_path=out)

    assert result.success
    assert out.stat().st_size > 0


# ---------------------------------------------------------------------------
# Tests — equation rendering
# ---------------------------------------------------------------------------


def test_pdf_with_equation_exports(manifest_with_equation, tmp_path):
    """Equations should be pre-rendered to images; PDF still exports."""
    exporter = PdfExporter()
    out = tmp_path / "output.pdf"
    result = exporter.export(manifest_with_equation, template=None, output_path=out)

    assert result.success
    assert out.stat().st_size > 0


# ---------------------------------------------------------------------------
# Tests — validation
# ---------------------------------------------------------------------------


def test_validate_valid_pdf(basic_manifest, tmp_path):
    exporter = PdfExporter()
    out = tmp_path / "output.pdf"
    exporter.export(basic_manifest, template=None, output_path=out)

    result = exporter.validate(out)
    assert result.valid


def test_validate_missing_pdf(tmp_path):
    exporter = PdfExporter()
    result = exporter.validate(tmp_path / "nonexistent.pdf")
    assert not result.valid


def test_validate_empty_pdf(tmp_path):
    exporter = PdfExporter()
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")

    result = exporter.validate(empty)
    assert not result.valid
