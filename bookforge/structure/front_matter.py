"""Front matter generators — Title Page, Copyright Page, Cover Page.

Uses Jinja templates from the loaded template directory when available.
Falls back to inline HTML only when no template is provided (tests, CLI).

Template files expected per template directory:
  copyright.html.jinja   — variables: isbn, eisbn, year, publisher_name,
                            publisher_address, publisher_email
  title_page.html.jinja  — variables: title, subtitle, authors, publisher_name, year

These templates are validated at template load time (templates/loader.py)
to ensure all referenced variables are defined in BookMetadata.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from bookforge.core.models import BookMetadata


def build_title_page(metadata: BookMetadata, template=None) -> str:
    """Generate title page HTML from Jinja template or fallback."""
    context = _metadata_to_context(metadata)

    if template:
        rendered = _render_jinja(template, "title_page.html.jinja", context)
        if rendered:
            return rendered

    # Fallback (no template loaded — tests, CLI without template)
    subtitle_part = f"<p class='subtitle'>{context.get('subtitle', '')}</p>" if context.get("subtitle") else ""
    authors_str = ", ".join(metadata.authors) if metadata.authors else ""
    return (
        f"<div class='title-page'>\n"
        f"<h1 class='book-title'>{_escape(metadata.title)}</h1>\n"
        f"{subtitle_part}\n"
        f"<p class='authors'>{_escape(authors_str)}</p>\n"
        f"<p class='publisher'>{_escape(metadata.publisher_name)}</p>\n"
        f"</div>"
    )


def build_copyright_page(metadata: BookMetadata, template=None) -> str:
    """Generate copyright page HTML from Jinja template or fallback."""
    context = _metadata_to_context(metadata)

    if template:
        rendered = _render_jinja(template, "copyright.html.jinja", context)
        if rendered:
            return rendered

    # Fallback
    isbn_line = f"<p>ISBN: {metadata.isbn}</p>" if metadata.isbn else ""
    eisbn_line = f"<p>eISBN: {metadata.eisbn}</p>" if metadata.eisbn else ""
    address_line = f"<p>{_escape(metadata.publisher_address)}</p>" if metadata.publisher_address else ""
    email_line = f"<p>{_escape(metadata.publisher_email)}</p>" if metadata.publisher_email else ""

    return (
        f"<div class='copyright-page'>\n"
        f"<p>Copyright &copy; {metadata.year} {_escape(metadata.publisher_name)}</p>\n"
        f"<p>All rights reserved.</p>\n"
        f"{isbn_line}\n{eisbn_line}\n{address_line}\n{email_line}\n"
        f"<p>Published by {_escape(metadata.publisher_name)}</p>\n"
        f"</div>"
    )


def build_cover_page(metadata: BookMetadata, template=None) -> str:
    """Generate cover page HTML — image or placeholder."""
    if metadata.cover_image and metadata.cover_image.exists():
        return (
            f"<div class='cover-page'>"
            f"<img src='{metadata.cover_image.name}' alt='Cover' class='cover-image'/>"
            f"</div>"
        )
    return (
        f"<div class='cover-page cover-placeholder'>"
        f"<h1>{_escape(metadata.title)}</h1>"
        f"</div>"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _metadata_to_context(metadata: BookMetadata) -> dict:
    """Convert BookMetadata to a Jinja template context dict."""
    title_parts = (metadata.title or "").split(":", 1)
    return {
        "title": title_parts[0].strip(),
        "subtitle": title_parts[1].strip() if len(title_parts) > 1 else None,
        "authors": metadata.authors or [],
        "isbn": metadata.isbn,
        "eisbn": metadata.eisbn,
        "publisher_name": metadata.publisher_name or "",
        "publisher_address": metadata.publisher_address,
        "publisher_email": metadata.publisher_email,
        "year": metadata.year or 2026,
    }


def _render_jinja(template, template_filename: str, context: dict) -> str | None:
    """Render a Jinja template file from the template directory.

    Returns None if the template file doesn't exist (caller uses fallback).
    """
    try:
        if hasattr(template, "jinja_env"):
            jinja_template = template.jinja_env.get_template(template_filename)
        elif hasattr(template, "directory"):
            env = Environment(
                loader=FileSystemLoader(str(template.directory)),
                autoescape=select_autoescape(["html", "jinja"]),
            )
            jinja_template = env.get_template(template_filename)
        else:
            return None
        return jinja_template.render(**context)
    except TemplateNotFound:
        return None
    except Exception:
        return None


def _escape(text: str) -> str:
    if not text:
        return ""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
