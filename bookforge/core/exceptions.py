"""Typed exceptions — one per pipeline stage.

The worker catches BookForgeError at the file boundary.
Stage-specific types let callers respond selectively.
"""


class BookForgeError(Exception):
    """Base exception for all BookForge errors."""


class IngestionError(BookForgeError):
    """Stage 1: failed to read or extract content from a file."""


class NormalizationError(BookForgeError):
    """Stage 2: failed to convert content to clean semantic HTML."""


class AssemblyError(BookForgeError):
    """Stage 3: failed to merge articles into a book."""


class AIError(BookForgeError):
    """Stage 4: AI call failed after all retries."""


class StructureError(BookForgeError):
    """Stage 5: failed to assemble book sections into a manifest."""


class ExportError(BookForgeError):
    """Stage 6: failed to render output in a target format."""


class MetadataError(BookForgeError):
    """Metadata reading or validation failed."""


class TemplateError(BookForgeError):
    """Template loading or application failed."""


class ConfigError(BookForgeError):
    """Configuration loading or validation failed."""
