"""Metadata validator — validates and transforms raw Excel metadata.

Responsibilities:
  - Validate required fields (title, author)
  - Strip author credentials (Dr., Ph.D., university affiliations)
  - Convert raw row dicts into BookMetadata instances
  - Parse compound fields (output_formats, input_files)
"""

from __future__ import annotations

import re
from pathlib import Path

from bookforge.core.exceptions import MetadataError
from bookforge.core.logging import get_logger
from bookforge.core.models import BookMetadata, JobConfig

logger = get_logger("metadata.validator")

# Prefixes to strip from author names
_PREFIX_PATTERN = re.compile(
    r"^(Dr\.?|Prof\.?|Professor|Mr\.?|Mrs\.?|Ms\.?|Sir|Dame)\s+",
    re.IGNORECASE,
)

# Suffixes to strip (after comma removal)
_SUFFIX_PATTERN = re.compile(
    r"\s+(Ph\.?D\.?|M\.?D\.?|M\.?Sc\.?|B\.?Sc\.?|MBA|FACP|FRCP|FRS|FRCSE?|DSc\.?)\b",
    re.IGNORECASE,
)


def strip_author_credentials(raw_name: str) -> str:
    """Strip academic/professional credentials from an author name.

    Client requirement: output contains only first/last name — no degrees,
    titles, or institutional affiliations.

    Raises:
        MetadataError: If the name is empty after stripping.
    """
    name = raw_name.strip()

    # Remove common prefixes
    name = _PREFIX_PATTERN.sub("", name)

    # Remove parenthetical content: "Name (University of ...)"
    name = re.sub(r"\s*\([^)]*\)", "", name)

    # Remove suffixes after comma: "Name, Ph.D., MIT"
    if "," in name:
        name = name.split(",")[0].strip()

    # Remove common suffix patterns still remaining
    name = _SUFFIX_PATTERN.sub("", name)

    # Normalize whitespace
    name = " ".join(name.split())

    if not name:
        raise MetadataError(
            f"Author name is empty after credential stripping: {raw_name!r}"
        )

    return name


def build_book_metadata(row: dict) -> BookMetadata:
    """Convert a raw Excel row dict into a BookMetadata instance.

    Applies validation and credential stripping.

    Raises:
        MetadataError: On missing required fields or invalid data.
    """
    # Title is optional — AI generates it if missing (per REQUIREMENTS.md §7.2)
    title = row.get("title")
    title = str(title).strip() if title else ""

    # Author — strip credentials
    raw_author = row.get("author_name")
    if raw_author:
        authors = [strip_author_credentials(str(raw_author))]
    else:
        authors = []

    # Optional fields
    isbn = _str_or_none(row.get("isbn"))
    eisbn = _str_or_none(row.get("eisbn"))
    publisher_name = str(row.get("publisher_name") or "").strip()
    publisher_address = _str_or_none(row.get("publisher_address"))
    publisher_email = _str_or_none(row.get("publisher_email"))

    year = row.get("year")
    if year is not None:
        try:
            year = int(year)
        except (ValueError, TypeError):
            raise MetadataError(f"Invalid year: {year!r}")
    else:
        year = 2026

    language = str(row.get("language") or "en").strip()

    # Chapter ordering — store the row index for source_row_indices.
    # Within one row's comma-separated file list, each file gets a unique
    # sub-index (row_idx * 1000 + position) to preserve list order.
    chapter_order: dict[str, int] = {}
    source_row_indices: dict[str, int] = {}

    input_files_raw = row.get("input_files")
    if input_files_raw:
        files = _parse_list_field(str(input_files_raw))
        row_idx = row.get("_row_index", 0)
        for i, f in enumerate(files):
            source_row_indices[f] = row_idx * 1000 + i

    chapter_order_raw = row.get("chapter_order")
    if chapter_order_raw is not None and input_files_raw:
        try:
            order_val = int(chapter_order_raw)
            files = _parse_list_field(str(input_files_raw))
            for i, f in enumerate(files):
                chapter_order[f] = order_val * 1000 + i
        except (ValueError, TypeError):
            pass  # ignore non-integer chapter_order

    return BookMetadata(
        title=title,
        authors=authors,
        isbn=isbn,
        eisbn=eisbn,
        publisher_name=publisher_name,
        publisher_address=publisher_address,
        publisher_email=publisher_email,
        year=year,
        language=language,
        chapter_order=chapter_order,
        source_row_indices=source_row_indices,
    )


def build_job_config(row: dict) -> JobConfig:
    """Extract JobConfig fields from a raw Excel row dict."""
    template = str(row.get("template") or "academic").strip()

    rewrite_percent = row.get("rewrite_percent")
    if rewrite_percent is not None:
        try:
            rewrite_percent = int(rewrite_percent)
        except (ValueError, TypeError):
            rewrite_percent = 0
    else:
        rewrite_percent = 0

    generate_preface = _parse_bool(row.get("generate_preface"), default=True)
    generate_ack = _parse_bool(row.get("generate_acknowledgement"), default=True)

    output_formats_raw = row.get("output_formats")
    if output_formats_raw:
        output_formats = _parse_list_field(str(output_formats_raw))
    else:
        output_formats = ["epub"]

    return JobConfig(
        template=template,
        rewrite_percent=rewrite_percent,
        generate_preface=generate_preface,
        generate_acknowledgement=generate_ack,
        output_formats=output_formats,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _str_or_none(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _parse_list_field(value: str) -> list[str]:
    """Parse a comma-separated or semicolon-separated list field."""
    if ";" in value:
        items = value.split(";")
    else:
        items = value.split(",")
    return [item.strip() for item in items if item.strip()]


def _parse_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("true", "yes", "1", "y"):
        return True
    if s in ("false", "no", "0", "n"):
        return False
    return default
