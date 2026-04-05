"""Core data models that flow between pipeline stages.

Each stage has a well-defined input/output contract:
  Stage 1 (Ingest)    → RawContent
  Stage 2 (Normalize) → NormalizedContent
  Stage 3 (Assemble)  → AssembledBook
  Stage 4 (AI)        → ProcessedContent
  Stage 5 (Structure) → BookManifest
  Stage 6 (Export)    → ExportResult
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------


class SectionRole(str, Enum):
    COVER = "cover"
    TITLE_PAGE = "title_page"
    COPYRIGHT = "copyright"
    PREFACE = "preface"
    ACKNOWLEDGEMENT = "acknowledgement"
    TABLE_OF_CONTENTS = "toc"
    CHAPTER = "chapter"
    INDEX = "index"


class ProtectedBlockType(str, Enum):
    EQUATION = "equation"
    TABLE = "table"
    FIGURE_CAPTION = "figure_caption"


@dataclass
class Asset:
    """An embedded file (image, font, etc.).

    Assets are always file-backed — data lives on disk in the job's temp
    directory, never in memory. This prevents OOM on large PDFs with many
    high-resolution images.
    """

    filename: str
    media_type: str
    file_path: Path
    size_bytes: int


@dataclass
class Heading:
    """A detected heading in the document content."""

    level: int
    text: str
    anchor_id: str


@dataclass
class ProtectedBlock:
    """Content that must survive AI rewriting untouched.

    During AI rewriting the block is replaced with a placeholder string
    (e.g. <<<PROTECTED_0>>>) and restored afterwards.
    """

    block_id: str
    block_type: ProtectedBlockType
    original_html: str
    source_format: str  # "latex", "mathml", "html_table", "image"


# ---------------------------------------------------------------------------
# Stage boundary models
# ---------------------------------------------------------------------------


@dataclass
class RawContent:
    """Output of Stage 1 (Ingest)."""

    text: str
    format_hint: str  # "html", "markdown", "plain", etc.
    assets: list[Asset] = field(default_factory=list)
    source_metadata: dict = field(default_factory=dict)
    source_path: Path = field(default_factory=lambda: Path("."))


@dataclass
class NormalizedContent:
    """Output of Stage 2 (Normalize).

    body_html is clean semantic HTML with bf-protected tags marking
    equations, tables, and figure captions.
    """

    body_html: str
    detected_title: str | None = None
    detected_headings: list[Heading] = field(default_factory=list)
    protected_blocks: list[ProtectedBlock] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)
    source_metadata: dict = field(default_factory=dict)
    source_path: Path = field(default_factory=lambda: Path("."))


@dataclass
class AssembledBook:
    """Output of Stage 3 (Assemble).

    Aggregates multiple NormalizedContent articles into a single book.
    article_titles[] is used by the AI stage to generate the book title.
    """

    body_html: str
    article_titles: list[str] = field(default_factory=list)
    chapter_headings: list[Heading] = field(default_factory=list)
    protected_blocks: list[ProtectedBlock] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)
    metadata: BookMetadata | None = None
    source_files: list[Path] = field(default_factory=list)


@dataclass
class ProcessedContent:
    """Output of Stage 4 (AI Processing).

    Carries all fields from AssembledBook that downstream stages need,
    so Stages 5 and 6 receive a single complete object rather than
    requiring out-of-band parameters that bypass Stage 4.
    """

    body_html: str
    generated_title: str | None = None
    generated_preface: str | None = None
    generated_acknowledgement: str | None = None
    ai_metadata: dict = field(default_factory=dict)
    # Passed through from AssembledBook — not modified by AI stage
    chapter_headings: list[Heading] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)


@dataclass
class BookSection:
    """One section of the final book."""

    role: SectionRole
    title: str
    content_html: str
    order: int


@dataclass
class BookManifest:
    """Output of Stage 5 (Structure). Input to Stage 6 (Export)."""

    sections: list[BookSection] = field(default_factory=list)
    metadata: BookMetadata | None = None
    assets: list[Asset] = field(default_factory=list)


@dataclass
class BookMetadata:
    """Metadata for the book — from Excel, config, or detection."""

    title: str = ""
    authors: list[str] = field(default_factory=list)
    isbn: str | None = None
    eisbn: str | None = None
    publisher_name: str = ""
    publisher_address: str | None = None
    publisher_email: str | None = None
    year: int = 2026
    language: str = "en"
    cover_image: Path | None = None
    chapter_order: dict[str, int] = field(default_factory=dict)
    source_row_indices: dict[str, int] = field(default_factory=dict)


@dataclass
class JobConfig:
    """Per-job configuration — from API, Excel, or defaults."""

    template: str = "academic"
    rewrite_percent: int = 0
    generate_title: bool = True
    generate_preface: bool = True
    generate_acknowledgement: bool = True
    generate_index: bool = False
    output_formats: list[str] = field(default_factory=lambda: ["epub"])
    max_concurrent_files: int = 4
    per_file_timeout_seconds: int = 300


@dataclass
class ExportResult:
    """Result of a single export operation."""

    format: str
    output_path: Path
    success: bool
    error: str | None = None


@dataclass
class ValidationResult:
    """Result of output file validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
