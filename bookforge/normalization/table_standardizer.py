"""Table Standardizer — third sub-step of Stage 2 (Normalize).

Normalises table markup and tags every <table> as bf-protected so the
AI rewriter leaves it untouched.
"""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from bookforge.core.models import ProtectedBlock, ProtectedBlockType


def standardize_tables(
    html: str, block_counter: int = 0
) -> tuple[str, list[ProtectedBlock], int]:
    """Normalise tables and mark them as protected blocks.

    Returns:
        (modified_html, new_protected_blocks, updated_counter)
    """
    soup = BeautifulSoup(html, "lxml")
    blocks: list[ProtectedBlock] = []

    for table in soup.find_all("table"):
        if not isinstance(table, Tag):
            continue

        # Normalise: ensure thead/tbody exist
        _ensure_thead_tbody(table)

        block_id = f"PROTECTED_{block_counter}"
        block_counter += 1

        # Tag as protected
        existing_classes = table.get("class", [])
        if isinstance(existing_classes, str):
            existing_classes = [existing_classes]
        table["class"] = list(existing_classes) + ["bf-protected"]
        table["data-type"] = "table"
        table["data-block-id"] = block_id

        blocks.append(
            ProtectedBlock(
                block_id=block_id,
                block_type=ProtectedBlockType.TABLE,
                original_html=str(table),
                source_format="html_table",
            )
        )

    return str(soup), blocks, block_counter


def _ensure_thead_tbody(table: Tag) -> None:
    """Ensure table has <thead> and <tbody> wrappers."""
    rows = table.find_all("tr", recursive=False)
    if not rows:
        # Rows may be directly in the table without thead/tbody
        rows = table.find_all("tr")

    has_thead = table.find("thead") is not None
    has_tbody = table.find("tbody") is not None

    if has_thead and has_tbody:
        return

    soup = table.__class__.__module__  # reference the parser via BeautifulSoup
    from bs4 import BeautifulSoup as BS

    # If no thead, treat the first row with <th> cells as the header
    if not has_thead and rows:
        first_row = rows[0]
        if first_row.find("th"):
            thead = BS("<thead></thead>", "lxml").find("thead")
            first_row.extract()
            thead.append(first_row)
            table.insert(0, thead)

    # Wrap remaining bare <tr> rows in <tbody>
    bare_rows = table.find_all("tr", recursive=False)
    if bare_rows and not has_tbody:
        tbody = BS("<tbody></tbody>", "lxml").find("tbody")
        for row in bare_rows:
            row.extract()
            tbody.append(row)
        table.append(tbody)
