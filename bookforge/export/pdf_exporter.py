"""PDF Exporter — Stage 6 for PDF output.

Produces high-quality digital PDF via WeasyPrint.
Equations are pre-rendered to images before PDF generation.

MVP scope: digital distribution and standard printing.
Phase 2: PrinceXML for press-ready PDF (bleed, CMYK, PDF/A).

WeasyPrint gotcha: always pass base_url=str(template.directory) so
@font-face url() references resolve relative to the template directory.
Without base_url, fonts 404 silently and WeasyPrint falls back to system
fonts without any warning.
"""

from __future__ import annotations

from pathlib import Path

from bookforge.core.exceptions import ExportError
from bookforge.core.models import (
    BookManifest,
    ExportResult,
    ValidationResult,
)
from bookforge.core.registry import register_exporter
from bookforge.export.base import BaseExporter
from bookforge.export.equation_renderer import render_equations_to_images

_FALLBACK_CSS = """
body { font-family: Georgia, serif; font-size: 11pt; line-height: 1.5; margin: 2cm; }
h1, h2, h3 { font-family: Arial, sans-serif; page-break-after: avoid; }
section.bf-chapter { page-break-before: always; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
table th, table td { border: 0.25pt solid #000; padding: 4pt 6pt; }
table thead { background-color: #f0f0f0; }
img { max-width: 100%; }
img.equation { vertical-align: middle; }
.cover-page { text-align: center; padding: 4cm 0; }
.title-page { text-align: center; padding: 3cm 0; page-break-after: always; }
.toc { page-break-after: always; }
"""


@register_exporter("pdf")
class PdfExporter(BaseExporter):
    """Renders BookManifest → PDF via WeasyPrint."""

    output_format = "pdf"

    def export(
        self,
        manifest: BookManifest,
        template=None,
        output_path: Path = None,
    ) -> ExportResult:
        if output_path is None:
            raise ExportError("output_path is required")

        try:
            from weasyprint import CSS, HTML
        except ImportError as exc:
            raise ExportError("WeasyPrint is not installed") from exc

        try:
            return self._export(manifest, template, output_path, HTML, CSS)
        except ExportError:
            raise
        except Exception as exc:
            raise ExportError(f"PDF export failed: {exc}") from exc

    def _export(self, manifest, template, output_path, HTML, CSS) -> ExportResult:
        # Pre-render equations to images
        temp_dir = output_path.parent / "eq_images"
        full_html, eq_assets = self._build_html_with_equations(manifest, temp_dir)

        # Merge equation assets into manifest assets (for image src resolution)
        all_assets = list(manifest.assets or []) + eq_assets

        # Determine CSS sources and base_url
        css_list = []
        base_url = str(output_path.parent)

        if template and hasattr(template, "styles_css") and template.styles_css.exists():
            css_list.append(CSS(filename=str(template.styles_css)))
            base_url = str(template.directory)
        else:
            css_list.append(CSS(string=_FALLBACK_CSS))

        if template and hasattr(template, "print_css") and template.print_css.exists():
            css_list.append(CSS(filename=str(template.print_css)))

        # Write assets to output directory for WeasyPrint to resolve
        asset_dir = output_path.parent / "images"
        asset_dir.mkdir(parents=True, exist_ok=True)
        for asset in all_assets:
            if asset.file_path.exists():
                dest = asset_dir / asset.filename
                if not dest.exists():
                    import shutil
                    shutil.copy2(asset.file_path, dest)

        # Render PDF
        output_path.parent.mkdir(parents=True, exist_ok=True)
        document = HTML(string=full_html, base_url=base_url).render(stylesheets=css_list)
        document.write_pdf(str(output_path))

        return ExportResult(format="pdf", output_path=output_path, success=True)

    def _build_html_with_equations(
        self, manifest: BookManifest, temp_dir: Path
    ) -> tuple[str, list]:
        """Assemble full HTML document and render equations to images."""
        sections_html: list[str] = []
        for section in sorted(manifest.sections, key=lambda s: s.order):
            sections_html.append(f"<section class='{section.role.value}'>{section.content_html}</section>")

        body = "\n".join(sections_html)

        # Render equations before final assembly
        body, eq_assets = render_equations_to_images(body, temp_dir)

        meta = manifest.metadata
        title = meta.title if meta else "Untitled"
        lang = meta.language if meta else "en"

        full_html = (
            f'<!DOCTYPE html>\n'
            f'<html lang="{lang}">\n'
            f'<head><meta charset="utf-8"/><title>{title}</title></head>\n'
            f'<body>\n{body}\n</body>\n</html>'
        )

        return full_html, eq_assets

    def validate(self, output_path: Path) -> ValidationResult:
        """Check the PDF exists and has non-zero size."""
        if not output_path.exists():
            return ValidationResult(valid=False, errors=["PDF file not created"])
        if output_path.stat().st_size == 0:
            return ValidationResult(valid=False, errors=["PDF file is empty"])
        return ValidationResult(valid=True)
