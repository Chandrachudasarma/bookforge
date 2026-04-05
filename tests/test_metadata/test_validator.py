"""Tests for metadata validator and author credential stripper.

Test cases for strip_author_credentials come from IMPLEMENTATION.md §9.2.
"""

import pytest

from bookforge.core.exceptions import MetadataError
from bookforge.metadata.validator import (
    build_book_metadata,
    build_job_config,
    strip_author_credentials,
)


# ---------------------------------------------------------------------------
# Author credential stripping — cases from IMPLEMENTATION.md
# ---------------------------------------------------------------------------


def test_strips_dr_and_phd():
    assert strip_author_credentials("Dr. John Smith, Ph.D., MIT") == "John Smith"


def test_strips_prof_and_university():
    assert strip_author_credentials("Prof. Jane Doe (University of Cambridge)") == "Jane Doe"


def test_strips_md_and_facp():
    assert strip_author_credentials("A. Kumar, M.D., FACP") == "A. Kumar"


def test_preserves_apostrophe():
    assert strip_author_credentials("Dr. Sarah O'Brien") == "Sarah O'Brien"


def test_strips_professor_prefix():
    assert strip_author_credentials("Professor Albert Einstein") == "Albert Einstein"


def test_strips_mr_prefix():
    assert strip_author_credentials("Mr. James Bond") == "James Bond"


def test_strips_msc_suffix():
    assert strip_author_credentials("Maria Garcia MSc") == "Maria Garcia"


def test_plain_name_unchanged():
    assert strip_author_credentials("John Smith") == "John Smith"


def test_raises_on_empty_result():
    with pytest.raises(MetadataError, match="empty after credential stripping"):
        strip_author_credentials("   ")


def test_normalizes_whitespace():
    assert strip_author_credentials("  Dr.   John   Smith  ") == "John Smith"


# ---------------------------------------------------------------------------
# build_book_metadata
# ---------------------------------------------------------------------------


def test_builds_basic_metadata():
    row = {"title": "My Book", "author_name": "Dr. Smith", "year": 2026}
    meta = build_book_metadata(row)
    assert meta.title == "My Book"
    assert meta.authors == ["Smith"]
    assert meta.year == 2026


def test_missing_title_defaults_to_empty():
    """Title is optional — AI generates it when empty."""
    meta = build_book_metadata({"author_name": "Smith"})
    assert meta.title == ""


def test_handles_all_optional_fields():
    row = {
        "title": "Full Book",
        "author_name": "Jane Doe",
        "isbn": "978-0-1234-5678-0",
        "eisbn": "978-0-1234-5679-7",
        "publisher_name": "Academic Press",
        "publisher_address": "123 Main St",
        "publisher_email": "info@press.com",
        "year": 2025,
        "language": "fr",
    }
    meta = build_book_metadata(row)
    assert meta.isbn == "978-0-1234-5678-0"
    assert meta.eisbn == "978-0-1234-5679-7"
    assert meta.publisher_name == "Academic Press"
    assert meta.publisher_address == "123 Main St"
    assert meta.publisher_email == "info@press.com"
    assert meta.language == "fr"


def test_defaults_year_to_2026():
    meta = build_book_metadata({"title": "Book"})
    assert meta.year == 2026


def test_defaults_language_to_en():
    meta = build_book_metadata({"title": "Book"})
    assert meta.language == "en"


def test_invalid_year_raises():
    with pytest.raises(MetadataError, match="Invalid year"):
        build_book_metadata({"title": "Book", "year": "not-a-year"})


def test_source_row_indices_populated():
    row = {
        "title": "Book",
        "input_files": "chapter1.html,chapter2.html",
        "_row_index": 3,
    }
    meta = build_book_metadata(row)
    # Each file gets a unique sub-index: row_idx * 1000 + position
    assert meta.source_row_indices == {"chapter1.html": 3000, "chapter2.html": 3001}


def test_chapter_order_populated():
    row = {
        "title": "Book",
        "input_files": "intro.html",
        "chapter_order": 2,
    }
    meta = build_book_metadata(row)
    assert meta.chapter_order == {"intro.html": 2000}


def test_within_row_file_ordering_preserved():
    """Files in a comma-separated list get ascending sub-indices."""
    row = {
        "title": "Book",
        "input_files": "ch3.html,ch1.html,ch2.html",
        "_row_index": 1,
    }
    meta = build_book_metadata(row)
    assert meta.source_row_indices["ch3.html"] < meta.source_row_indices["ch1.html"]
    assert meta.source_row_indices["ch1.html"] < meta.source_row_indices["ch2.html"]


# ---------------------------------------------------------------------------
# build_job_config
# ---------------------------------------------------------------------------


def test_builds_default_job_config():
    config = build_job_config({})
    assert config.template == "academic"
    assert config.rewrite_percent == 0
    assert config.output_formats == ["epub"]


def test_parses_output_formats():
    config = build_job_config({"output_formats": "epub,docx,pdf"})
    assert config.output_formats == ["epub", "docx", "pdf"]


def test_parses_semicolon_separated_formats():
    config = build_job_config({"output_formats": "epub;pdf"})
    assert config.output_formats == ["epub", "pdf"]


def test_parses_rewrite_percent():
    config = build_job_config({"rewrite_percent": 20})
    assert config.rewrite_percent == 20


def test_parses_generate_preface_bool():
    assert build_job_config({"generate_preface": "true"}).generate_preface is True
    assert build_job_config({"generate_preface": "false"}).generate_preface is False
    assert build_job_config({"generate_preface": "yes"}).generate_preface is True
    assert build_job_config({"generate_preface": "no"}).generate_preface is False
