"""DOCX ingester — Stage 1 for .docx files.

Uses python-docx for fine-grained control over style mapping and image
extraction. Style names are mapped to semantic HTML tags.

DOCX style → HTML mapping:
  Heading 1        → <h1>
  Heading 2        → <h2>
  Heading 3        → <h3>
  Normal / Body Text → <p>
  Caption          → <figcaption>
  Code / Preformatted → <pre><code>
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.table import Table

from bookforge.core.exceptions import IngestionError
from bookforge.core.models import Asset, RawContent
from bookforge.core.registry import register_ingester
from bookforge.ingestion.base import BaseIngester

# python-docx style name → HTML tag
_HEADING_STYLES = {
    "heading 1": "h1",
    "heading 2": "h2",
    "heading 3": "h3",
    "heading 4": "h4",
    "heading 5": "h5",
    "heading 6": "h6",
    "title": "h1",
    "subtitle": "h2",
}

_CODE_STYLES = {"code", "preformatted", "code text", "verbatim"}
_CAPTION_STYLES = {"caption", "figure caption", "table caption"}


@register_ingester("docx")
class DocxIngester(BaseIngester):
    """Reads DOCX files and converts to HTML preserving structure."""

    supported_extensions = [".docx"]
    supported_mimetypes = [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ]

    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".docx"

    def ingest(self, file_path: Path, config: dict) -> RawContent:
        try:
            doc = Document(str(file_path))
        except Exception as exc:
            raise IngestionError(f"Cannot open DOCX: {file_path.name}: {exc}") from exc

        temp_dir = Path(config.get("pipeline", {}).get("temp_dir", "/tmp/bookforge"))
        temp_dir.mkdir(parents=True, exist_ok=True)

        html_parts: list[str] = []
        assets: list[Asset] = []
        image_counter = 0

        for block in doc.element.body:
            tag = block.tag.split("}")[-1] if "}" in block.tag else block.tag

            if tag == "p":
                para = Paragraph(block, doc)
                para_html, para_assets = _render_paragraph(
                    para, doc, temp_dir, image_counter
                )
                image_counter += len(para_assets)
                if para_html:
                    html_parts.append(para_html)
                assets.extend(para_assets)

            elif tag == "tbl":
                table = Table(block, doc)
                html_parts.append(_render_table(table))

        return RawContent(
            text="\n".join(html_parts),
            format_hint="html",
            assets=assets,
            source_metadata={"original_format": "docx"},
            source_path=file_path,
        )


# ---------------------------------------------------------------------------
# Paragraph rendering
# ---------------------------------------------------------------------------


def _render_paragraph(
    para: Paragraph,
    doc: Document,
    temp_dir: Path,
    image_counter: int,
) -> tuple[str, list[Asset]]:
    style_name = (para.style.name or "").lower().strip()
    assets: list[Asset] = []

    # Collect inline images
    images = para._element.findall(".//" + qn("a:blip"))
    inline_imgs: list[str] = []
    for blip in images:
        embed = blip.get(qn("r:embed"))
        if embed:
            try:
                rel = doc.part.rels.get(embed)
                if rel:
                    image_data = rel.target_part.blob
                    img_name = f"docx_img_{image_counter + len(inline_imgs)}.png"
                    img_path = temp_dir / img_name
                    img_path.write_bytes(image_data)
                    content_type = rel.target_part.content_type
                    media_type = content_type if "/" in content_type else "image/png"
                    asset = Asset(
                        filename=img_name,
                        media_type=media_type,
                        file_path=img_path,
                        size_bytes=len(image_data),
                    )
                    assets.append(asset)
                    inline_imgs.append(
                        f'<figure><img src="{img_name}" alt=""/></figure>'
                    )
            except Exception:
                pass  # skip unresolvable images

    if inline_imgs:
        return "\n".join(inline_imgs), assets

    text = para.text.strip()
    if not text:
        return "", assets

    # Map style to HTML tag
    if style_name in _HEADING_STYLES:
        tag = _HEADING_STYLES[style_name]
        return f"<{tag}>{_escape(text)}</{tag}>", assets

    if style_name in _CAPTION_STYLES:
        return f"<figcaption>{_escape(text)}</figcaption>", assets

    if style_name in _CODE_STYLES:
        return f"<pre><code>{_escape(text)}</code></pre>", assets

    # Inline formatting
    inner_html = _render_runs(para)
    if not inner_html.strip():
        return "", assets

    return f"<p>{inner_html}</p>", assets


def _render_runs(para: Paragraph) -> str:
    """Render paragraph runs with bold/italic inline formatting."""
    parts: list[str] = []
    for run in para.runs:
        text = _escape(run.text)
        if not text:
            continue
        if run.bold and run.italic:
            text = f"<strong><em>{text}</em></strong>"
        elif run.bold:
            text = f"<strong>{text}</strong>"
        elif run.italic:
            text = f"<em>{text}</em>"
        parts.append(text)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------


def _render_table(table: Table) -> str:
    rows_html: list[str] = []
    for i, row in enumerate(table.rows):
        cells: list[str] = []
        for cell in row.cells:
            text = _escape(cell.text.strip())
            tag = "th" if i == 0 else "td"
            cells.append(f"<{tag}>{text}</{tag}>")
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    if not rows_html:
        return ""

    thead = f"<thead>{rows_html[0]}</thead>"
    tbody_rows = rows_html[1:]
    tbody = f"<tbody>{''.join(tbody_rows)}</tbody>" if tbody_rows else ""

    return f"<table>{thead}{tbody}</table>"


def _escape(text: str) -> str:
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
