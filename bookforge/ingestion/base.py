"""Abstract base class for all ingesters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from bookforge.core.models import RawContent


class BaseIngester(ABC):
    """Extracts raw content from a specific file format.

    Ingesters are responsible only for extraction — no cleaning,
    structuring, or normalisation. That is Stage 2's job.
    """

    supported_extensions: list[str] = []
    supported_mimetypes: list[str] = []

    @abstractmethod
    def can_handle(self, file_path: Path) -> bool:
        """Return True if this ingester can process the given file."""

    @abstractmethod
    def ingest(self, file_path: Path, config: dict) -> RawContent:
        """Extract content from the file and return RawContent.

        Assets (images, etc.) must be written to disk in config["temp_dir"]
        and referenced by Path — never held as bytes in memory.
        """
