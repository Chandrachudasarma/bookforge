"""EPUB Exporter — Stage 6 for EPUB output.

Builds a valid EPUB 3.0 package using ebooklib, with optional Calibre
post-processing if installed. Template CSS and fonts are embedded when
a template is provided.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from ebooklib import epub

from bookforge.core.exceptions import ExportError
from bookforge.core.models import (
    BookManifest,
    ExportResult,
    SectionRole,
    ValidationResult,
)
from bookforge.core.registry import register_exporter
from bookforge.export.base import BaseExporter

# Minimal fallback CSS when no template is loaded
_FALLBACK_CSS = """
body { font-family: Georgia, serif; font-size: 1em; line-height: 1.5; margin: 2em; }
h1, h2, h3 { font-family: Arial, sans-serif; }
table { border-collapse: collapse; width: 100%; }
table th, table td { border: 1px solid #333; padding: 4px 8px; }
table thead { background-color: #f0f0f0; }
.cover-page { text-align: center; padding: 4em 0; }
.title-page { text-align: center; padding: 3em 0; }
.toc ol { list-style: none; padding: 0; }
.toc li { padding: 0.3em 0; }
.toc .toc-h2 { padding-left: 2em; }
"""


@register_exporter("epub")
class EpubExporter(BaseExporter):
    """Renders BookManifest → EPUB 3.0 via ebooklib."""

    output_format = "epub"

    def export(
        self,
        manifest: BookManifest,
        template=None,
        output_path: Path = None,
    ) -> ExportResult:
        if output_path is None:
            raise ExportError("output_path is required")

        try:
            return self._export(manifest, template, output_path)
        except ExportError:
            raise
        except Exception as exc:
            raise ExportError(f"EPUB export failed: {exc}") from exc

    def _export(self, manifest: BookManifest, template, output_path: Path) -> ExportResult:
        book = epub.EpubBook()
        meta = manifest.metadata

        # --- Metadata ---
        book.set_identifier(meta.eisbn or str(uuid4()))
        book.set_title(meta.title or "Untitled")
        book.set_language(meta.language or "en")
        for author in (meta.authors or []):
            book.add_author(author)
        if meta.publisher_name:
            book.add_metadata("DC", "publisher", meta.publisher_name)
        if meta.year:
            book.add_metadata("DC", "date", str(meta.year))

        # --- CSS ---
        css_content = _FALLBACK_CSS
        if template and hasattr(template, "styles_css") and template.styles_css.exists():
            css_content = template.styles_css.read_text(encoding="utf-8")

        style_item = epub.EpubItem(
            uid="style",
            file_name="style/main.css",
            media_type="text/css",
            content=css_content.encode("utf-8"),
        )
        book.add_item(style_item)

        # --- Fonts ---
        if template and hasattr(template, "fonts"):
            for font_path in template.fonts:
                if font_path.exists():
                    font_item = epub.EpubItem(
                        uid=f"font_{font_path.stem}",
                        file_name=f"fonts/{font_path.name}",
                        media_type=_font_media_type(font_path.suffix),
                        content=font_path.read_bytes(),
                    )
                    book.add_item(font_item)

        # --- Assets (images) ---
        for asset in (manifest.assets or []):
            if asset.file_path.exists():
                img_item = epub.EpubItem(
                    uid=f"asset_{asset.filename}",
                    file_name=f"images/{asset.filename}",
                    media_type=asset.media_type,
                    content=asset.file_path.read_bytes(),
                )
                book.add_item(img_item)

        # --- Book sections → EPUB documents ---
        epub_items: list[epub.EpubHtml] = []
        spine: list = ["nav"]

        for section in sorted(manifest.sections, key=lambda s: s.order):
            file_name = f"{section.role.value}_{section.order}.xhtml"
            html_content = _wrap_section_html(section.content_html, section.title, "style/main.css")

            item = epub.EpubHtml(
                uid=f"section_{section.order}",
                title=section.title,
                file_name=file_name,
                content=html_content.encode("utf-8"),
                lang=meta.language or "en",
            )
            item.add_item(style_item)
            book.add_item(item)
            epub_items.append(item)
            spine.append(item)

        # --- TOC and spine ---
        toc_items = [
            epub.Link(f"{s.role.value}_{s.order}.xhtml", s.title, f"section_{s.order}")
            for s in sorted(manifest.sections, key=lambda s: s.order)
            if s.role == SectionRole.CHAPTER
        ]
        book.toc = toc_items
        book.spine = spine
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # --- Write ---
        output_path.parent.mkdir(parents=True, exist_ok=True)
        epub.write_epub(str(output_path), book)

        # --- Optional Calibre polish ---
        config_calibre = True
        if template and hasattr(template, "config"):
            config_calibre = getattr(template.config, "calibre_polish", True)

        if config_calibre:
            output_path = _calibre_polish(output_path)

        return ExportResult(format="epub", output_path=output_path, success=True)

    def validate(self, output_path: Path) -> ValidationResult:
        """Run epubcheck if installed; skip silently if not."""
        epubcheck = shutil.which("epubcheck")
        if not epubcheck:
            return ValidationResult(valid=True, warnings=["epubcheck not installed"])

        result = subprocess.run(
            ["epubcheck", str(output_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        errors = [l for l in result.stderr.splitlines() if "ERROR" in l]
        warnings = [l for l in result.stderr.splitlines() if "WARNING" in l]
        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wrap_section_html(content: str, title: str, css_path: str) -> str:
    """Wrap a section's content in strict XHTML for ebooklib.

    ebooklib internally re-parses content with lxml's XMLParser (strict).
    AI-rewritten text can contain &nbsp;, unescaped &, and other HTML-isms
    that break strict XML parsing. Fix: parse as lenient HTML, serialize
    as strict XML.
    """
    from lxml import etree, html as lxml_html

    # Build the full XHTML document first
    raw_xhtml = (
        '<html><head>'
        f'<title>{title}</title>'
        f'<link rel="stylesheet" type="text/css" href="{css_path}"/>'
        '</head>'
        f'<body>{content}</body></html>'
    )

    try:
        # Parse as HTML (lenient — handles &nbsp;, unescaped &, etc.)
        doc = lxml_html.document_fromstring(raw_xhtml)
        # Serialize as strict XML (ebooklib-safe)
        clean = etree.tostring(
            doc, encoding="unicode", method="xml",
            xml_declaration=False,
        )
        # Add XHTML namespace and XML declaration
        clean = clean.replace("<html>", '<html xmlns="http://www.w3.org/1999/xhtml">', 1)
        return '<?xml version="1.0" encoding="utf-8"?>\n' + clean
    except Exception:
        # Last resort fallback — escape obvious problems
        safe = content.replace("&nbsp;", "&#160;")
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml">\n'
            f"<head><title>{title}</title>"
            f'<link rel="stylesheet" type="text/css" href="{css_path}"/>'
            "</head>\n"
            f"<body>{safe}</body></html>"
        )


def _font_media_type(suffix: str) -> str:
    return {
        ".ttf": "font/ttf",
        ".otf": "font/otf",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
    }.get(suffix.lower(), "application/octet-stream")


def _calibre_polish(epub_path: Path) -> Path:
    """Run Calibre ebook-polish if available. Return polished path or original."""
    binary = shutil.which("ebook-polish")
    if not binary:
        # Check macOS app bundle location
        macos_path = "/Applications/calibre.app/Contents/MacOS/ebook-polish"
        if Path(macos_path).exists():
            binary = macos_path

    if not binary:
        return epub_path

    polished = epub_path.with_stem(epub_path.stem + "_polished")
    try:
        result = subprocess.run(
            [binary, str(epub_path), str(polished)],
            capture_output=True,
            timeout=120,
        )
        if result.returncode == 0 and polished.exists():
            return polished
    except (subprocess.TimeoutExpired, OSError):
        pass

    return epub_path
