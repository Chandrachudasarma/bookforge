"""Structure Builder — Stage 5 of the pipeline.

Assembles the final BookManifest from ProcessedContent and BookMetadata.
Sections are included or excluded based on what was actually generated —
no hardcoded assumptions about what will exist.

Section order (per REQUIREMENTS §5):
  1. Cover
  2. Title Page
  3. Copyright
  4. Preface        ← only if generated
  5. Acknowledgement ← only if generated
  6. Table of Contents
  7. Chapters (N)
  8. Index          ← only if config.generate_index
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from bookforge.core.exceptions import StructureError
from bookforge.core.models import (
    BookManifest,
    BookMetadata,
    BookSection,
    JobConfig,
    ProcessedContent,
    SectionRole,
)
from bookforge.structure.front_matter import (
    build_copyright_page,
    build_cover_page,
    build_title_page,
)
from bookforge.structure.toc_generator import generate_toc_html


def build_manifest(
    content: ProcessedContent,
    metadata: BookMetadata,
    config: JobConfig,
    template=None,
) -> BookManifest:
    """Assemble the BookManifest from ProcessedContent.

    headings and assets come from content.chapter_headings / content.assets,
    which are passed through from AssembledBook by the AI stage.
    """
    try:
        return _build(content, metadata, config, template)
    except StructureError:
        raise
    except Exception as exc:
        raise StructureError(f"Structure building failed: {exc}") from exc


def _build(
    content: ProcessedContent,
    metadata: BookMetadata,
    config: JobConfig,
    template=None,
) -> BookManifest:
    headings = content.chapter_headings
    assets = content.assets
    sections: list[BookSection] = []
    order = 0

    def add(role: SectionRole, title: str, html: str) -> None:
        nonlocal order
        sections.append(BookSection(role=role, title=title, content_html=html, order=order))
        order += 1

    # Always included
    add(SectionRole.COVER, "Cover", build_cover_page(metadata, template))
    add(SectionRole.TITLE_PAGE, "Title Page", build_title_page(metadata, template))
    add(SectionRole.COPYRIGHT, "Copyright", build_copyright_page(metadata, template))

    # Conditionally included — AI-generated text may be plain text without
    # HTML tags. Wrap in <p> tags paragraph-by-paragraph for valid XHTML.
    if content.generated_preface:
        add(SectionRole.PREFACE, "Preface", _ensure_html(content.generated_preface))

    if content.generated_acknowledgement:
        add(SectionRole.ACKNOWLEDGEMENT, "Acknowledgements", _ensure_html(content.generated_acknowledgement))

    # TOC (always included)
    toc_html = generate_toc_html(headings)
    add(SectionRole.TABLE_OF_CONTENTS, "Table of Contents", toc_html)

    # Chapters
    for chapter_html, chapter_title in _split_chapters(content.body_html):
        add(SectionRole.CHAPTER, chapter_title, chapter_html)

    # Index (optional — Phase 2)
    if config.generate_index:
        add(SectionRole.INDEX, "Index", "<div class='index'><p>Index pending.</p></div>")

    return BookManifest(sections=sections, metadata=metadata, assets=assets)


def _split_chapters(body_html: str) -> list[tuple[str, str]]:
    """Split body_html at <section class="bf-chapter"> boundaries.

    Returns list of (chapter_html, chapter_title).
    """
    soup = BeautifulSoup(body_html, "lxml")
    chapters = soup.find_all("section", class_="bf-chapter")

    if not chapters:
        # Single article case — treat entire body as one chapter
        title = _extract_first_heading(body_html) or "Chapter 1"
        return [(body_html, title)]

    result: list[tuple[str, str]] = []
    for chapter in chapters:
        title = _extract_first_heading(str(chapter)) or chapter.get("data-source", "Chapter")
        result.append((str(chapter), title))

    return result


def _ensure_html(text: str) -> str:
    """Wrap plain text in <p> tags if it doesn't contain HTML block elements."""
    if "<p>" in text or "<div>" in text or "<h1>" in text:
        return text
    # Plain text from AI — split on double newlines into paragraphs
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if not paragraphs:
        return f"<p>{text}</p>"
    return "\n".join(f"<p>{p}</p>" for p in paragraphs)


def _extract_first_heading(html: str) -> str | None:
    """Extract text of the first h1 in the HTML, if present."""
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return None
