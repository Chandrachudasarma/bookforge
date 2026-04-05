"""Abstract base class for all exporters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from bookforge.core.models import BookManifest, ExportResult, ValidationResult


class BaseExporter(ABC):
    """Renders a BookManifest into a specific output format."""

    output_format: str = ""

    @abstractmethod
    def export(
        self,
        manifest: BookManifest,
        template=None,
        output_path: Path = None,
    ) -> ExportResult:
        """Render the book to the target format.

        Args:
            manifest:     Fully assembled BookManifest.
            template:     Loaded Template object (may be None for tests).
            output_path:  Destination file path.
        """

    @abstractmethod
    def validate(self, output_path: Path) -> ValidationResult:
        """Validate the produced output file."""
