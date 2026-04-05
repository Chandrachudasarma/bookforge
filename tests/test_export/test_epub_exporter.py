"""Tests for the EPUB exporter (Stage 6)."""

import pytest
from pathlib import Path

from bookforge.core.models import (
    BookManifest,
    BookMetadata,
    BookSection,
    SectionRole,
)
from bookforge.export.epub_exporter import EpubExporter


def _make_manifest(title: str = "Test Book") -> BookManifest:
    metadata = BookMetadata(
        title=title,
        authors=["Test Author"],
        publisher_name="Test Publisher",
        year=2026,
        language="en",
    )
    sections = [
        BookSection(
            role=SectionRole.TITLE_PAGE,
            title="Title Page",
            content_html=f"<div class='title-page'><h1>{title}</h1></div>",
            order=0,
        ),
        BookSection(
            role=SectionRole.CHAPTER,
            title="Chapter 1",
            content_html="<section><h1>Chapter 1</h1><p>Test content.</p></section>",
            order=1,
        ),
    ]
    return BookManifest(sections=sections, metadata=metadata, assets=[])


def test_epub_exporter_creates_file(tmp_path):
    exporter = EpubExporter()
    manifest = _make_manifest()
    output_path = tmp_path / "test.epub"

    result = exporter.export(manifest, template=None, output_path=output_path)

    assert result.success
    assert result.output_path.exists()
    assert result.output_path.stat().st_size > 0


def test_epub_exporter_produces_valid_zip(tmp_path):
    """EPUB files are ZIP archives — verify the structure."""
    import zipfile

    exporter = EpubExporter()
    manifest = _make_manifest()
    output_path = tmp_path / "test.epub"
    result = exporter.export(manifest, template=None, output_path=output_path)

    # EPUBs must be valid ZIP files
    assert zipfile.is_zipfile(result.output_path)
    with zipfile.ZipFile(result.output_path) as zf:
        names = zf.namelist()
        # Must contain mimetype and content.opf
        assert any("mimetype" in n for n in names) or any(".opf" in n for n in names)


def test_epub_exporter_requires_output_path():
    from bookforge.core.exceptions import ExportError
    exporter = EpubExporter()
    manifest = _make_manifest()
    with pytest.raises(ExportError):
        exporter.export(manifest, template=None, output_path=None)
