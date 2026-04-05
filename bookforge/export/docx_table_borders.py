"""DOCX table border application.

python-docx has no high-level border API. Borders are applied via
low-level XML manipulation using the OOXML schema.

Border size unit: 1/8th of a point. sz=2 → 0.25pt (hairline).
"""

from __future__ import annotations

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def apply_table_borders(doc: Document, border_width: int = 2) -> None:
    """Apply hairline grid borders to every table in the document.

    Args:
        doc:          The python-docx Document object to modify in-place.
        border_width: Border size in 1/8pt units. 2 = 0.25pt (hairline).
    """
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                _set_cell_borders(cell, border_width)


def _set_cell_borders(cell, sz: int) -> None:
    """Apply border to all edges of a single table cell."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()

    # Remove any existing border definition
    existing = tcPr.find(qn("w:tcBorders"))
    if existing is not None:
        tcPr.remove(existing)

    tcBorders = OxmlElement("w:tcBorders")

    for edge in ("top", "bottom", "start", "end", "insideH", "insideV"):
        border = OxmlElement(f"w:{edge}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), str(sz))
        border.set(qn("w:space"), "0")
        border.set(qn("w:color"), "000000")
        tcBorders.append(border)

    tcPr.append(tcBorders)
