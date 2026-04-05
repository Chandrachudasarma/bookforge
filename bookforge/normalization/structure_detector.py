"""Structure Detector — second sub-step of Stage 2 (Normalize).

Detects headings, wraps content in a semantic <article> element,
and promotes the first heading to the detected_title.
"""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from bookforge.core.models import Heading


def detect_structure(html: str, source_path: Path) -> tuple[str, str | None, list[Heading]]:
    """Wrap content in <article>, detect title, and collect headings.

    Returns:
        (structured_html, detected_title, headings)
    """
    soup = BeautifulSoup(html, "lxml")
    body = soup.find("body") or soup

    headings: list[Heading] = []
    detected_title: str | None = None

    for tag in body.find_all(re.compile(r"^h[1-6]$")):
        if not isinstance(tag, Tag):
            continue
        level = int(tag.name[1])
        text = tag.get_text(separator=" ", strip=True)
        anchor_id = _slugify(text)

        # Ensure anchor id is present for TOC linking
        if not tag.get("id"):
            tag["id"] = anchor_id

        heading = Heading(level=level, text=text, anchor_id=anchor_id)
        headings.append(heading)

        # First h1 becomes the detected title
        if detected_title is None and level == 1:
            detected_title = text

    # Wrap in <article> with source attribution
    article = soup.new_tag(
        "article",
        attrs={
            "data-source": source_path.name,
            "data-type": "chapter",
        },
    )

    # Move all body children into the article
    children = list(body.children)
    for child in children:
        child.extract()
        article.append(child)

    result_soup = BeautifulSoup("<html><body></body></html>", "lxml")
    result_soup.body.append(article)

    return str(result_soup.body), detected_title, headings


def _slugify(text: str) -> str:
    """Convert heading text to a URL-safe anchor id."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = slug.strip("-")
    return slug or "section"
