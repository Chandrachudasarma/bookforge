"""Assembler — Stage 3 of the pipeline.

Merges multiple NormalizedContent articles into a single AssembledBook.
This is the per-file → per-book boundary: everything before this stage
runs per-file in parallel; everything after runs per-book sequentially.

Responsibilities:
- Order articles (by Excel chapter_order → row order → filename alpha)
- Wrap each article in <section class="bf-chapter">
- Promote detected_title to <h1> if absent
- Renumber protected block IDs to be globally unique
- Deduplicate assets across all articles
- Collect all article_titles[] for AI title generation
"""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup

from bookforge.core.exceptions import AssemblyError
from bookforge.core.models import AssembledBook, BookMetadata, Heading, NormalizedContent
from bookforge.assembly.deduplicator import deduplicate_assets, renumber_protected_blocks
from bookforge.assembly.ordering import order_articles


def assemble(
    articles: list[NormalizedContent],
    metadata: BookMetadata | None = None,
) -> AssembledBook:
    """Merge articles into one AssembledBook."""
    if not articles:
        raise AssemblyError("Cannot assemble: no articles provided")

    try:
        return _assemble(articles, metadata)
    except AssemblyError:
        raise
    except Exception as exc:
        raise AssemblyError(f"Assembly failed: {exc}") from exc


def _assemble(
    articles: list[NormalizedContent],
    metadata: BookMetadata | None,
) -> AssembledBook:
    # 1. Order articles
    ordered = order_articles(articles, metadata)

    # 2. Renumber protected blocks so IDs are globally unique
    ordered = renumber_protected_blocks(ordered)

    # 3. Deduplicate assets
    all_assets, rename_map = deduplicate_assets(ordered)

    # 4. Build merged body_html — each article becomes one chapter section
    chapter_sections: list[str] = []
    article_titles: list[str] = []
    all_headings: list[Heading] = []
    all_protected = []

    for article in ordered:
        title = article.detected_title or article.source_path.stem
        article_titles.append(title)
        all_headings.extend(article.detected_headings)
        all_protected.extend(article.protected_blocks)

        chapter_html = _wrap_as_chapter(
            article.body_html,
            title=title,
            source_name=article.source_path.name,
            rename_map=rename_map,
        )
        chapter_sections.append(chapter_html)

    body_html = "\n".join(chapter_sections)

    return AssembledBook(
        body_html=body_html,
        article_titles=article_titles,
        chapter_headings=all_headings,
        protected_blocks=all_protected,
        assets=all_assets,
        metadata=metadata,
        source_files=[a.source_path for a in ordered],
    )


def _wrap_as_chapter(
    article_html: str,
    title: str,
    source_name: str,
    rename_map: dict[str, str],
) -> str:
    """Wrap article HTML in a chapter <section> and update asset src refs."""
    soup = BeautifulSoup(article_html, "lxml")
    body = soup.find("body") or soup

    # Apply asset renames
    for img in body.find_all("img", src=True):
        old_src = img["src"]
        if old_src in rename_map:
            img["src"] = rename_map[old_src]

    # Extract inner content of the <article> tag if present
    article_tag = body.find("article")
    inner_html = str(article_tag) if article_tag else str(body)

    # Promote title to h1 if not already present
    inner_soup = BeautifulSoup(inner_html, "lxml")
    has_h1 = inner_soup.find("h1") is not None

    if not has_h1:
        h1 = f'<h1 id="{_slugify(title)}">{title}</h1>\n'
    else:
        h1 = ""

    # Unwrap the outer <article> since we're re-wrapping in <section>
    if article_tag:
        content_html = article_tag.decode_contents()
    else:
        content_html = str(body)

    return (
        f'<section class="bf-chapter" data-source="{source_name}">\n'
        f"{h1}"
        f"{content_html}\n"
        f"</section>"
    )


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-") or "chapter"
