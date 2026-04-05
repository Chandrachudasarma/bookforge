"""TOC Generator — builds a Table of Contents from chapter headings."""

from __future__ import annotations

from bookforge.core.models import Heading


def generate_toc_html(headings: list[Heading], title: str = "Table of Contents") -> str:
    """Generate an HTML table of contents from a flat list of headings.

    Only h1 and h2 headings are included to keep the TOC readable.
    """
    entries = [h for h in headings if h.level <= 2]
    if not entries:
        return f"<nav class='toc'><h2>{title}</h2><p>No chapters found.</p></nav>"

    items: list[str] = []
    for heading in entries:
        indent_class = "toc-h1" if heading.level == 1 else "toc-h2"
        items.append(
            f'<li class="{indent_class}">'
            f'<a href="#{heading.anchor_id}">{heading.text}</a>'
            f"</li>"
        )

    return (
        f"<nav class='toc'>\n"
        f"<h2>{title}</h2>\n"
        f"<ol>\n"
        + "\n".join(items)
        + "\n</ol>\n</nav>"
    )
