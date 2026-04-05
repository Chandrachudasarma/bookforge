"""Plugin registry for replaceable pipeline components.

Components register at import time via decorators. The pipeline resolves
them by name at runtime from config. No code changes needed to swap
an OCR engine, AI provider, or export format.

Usage:

    @register_ingester("html")
    class HtmlIngester(BaseIngester): ...

    @register_exporter("epub")
    class EpubExporter(BaseExporter): ...

    # Resolve at runtime:
    ingester = get_ingester_for_file(Path("doc.html"))
    exporter = get_exporter("epub")
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from bookforge.core.exceptions import ConfigError, IngestionError

if TYPE_CHECKING:
    from bookforge.ingestion.base import BaseIngester
    from bookforge.ingestion.ocr.base import BaseOCREngine
    from bookforge.ai.base import BaseAIProvider
    from bookforge.export.base import BaseExporter


_ingesters: dict[str, type] = {}
_ocr_engines: dict[str, type] = {}
_ai_providers: dict[str, type] = {}
_exporters: dict[str, type] = {}


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def register_ingester(name: str):
    """Register an ingester implementation under a format name."""
    def decorator(cls):
        _ingesters[name] = cls
        return cls
    return decorator


def register_ocr_engine(name: str):
    """Register an OCR engine implementation."""
    def decorator(cls):
        _ocr_engines[name] = cls
        return cls
    return decorator


def register_ai_provider(name: str):
    """Register an AI provider implementation."""
    def decorator(cls):
        _ai_providers[name] = cls
        return cls
    return decorator


def register_exporter(name: str):
    """Register an exporter implementation under a format name."""
    def decorator(cls):
        _exporters[name] = cls
        return cls
    return decorator


# ---------------------------------------------------------------------------
# Resolvers
# ---------------------------------------------------------------------------


def get_ingester_for_file(file_path: Path) -> "BaseIngester":
    """Detect file format and return the appropriate ingester instance."""
    from bookforge.ingestion.detector import detect_format
    fmt = detect_format(file_path)
    cls = _ingesters.get(fmt)
    if cls is None:
        raise IngestionError(
            f"No ingester registered for format '{fmt}' (file: {file_path.name})"
        )
    return cls()


def get_ocr_engine(name: str) -> "BaseOCREngine":
    cls = _ocr_engines.get(name)
    if cls is None:
        raise ConfigError(f"No OCR engine registered: '{name}'")
    return cls()


def get_ai_provider(name: str, config) -> "BaseAIProvider":
    cls = _ai_providers.get(name)
    if cls is None:
        raise ConfigError(f"No AI provider registered: '{name}'")
    return cls(config)


def get_exporter(name: str) -> "BaseExporter":
    cls = _exporters.get(name)
    if cls is None:
        raise ConfigError(f"No exporter registered: '{name}'")
    return cls()


def list_exporters() -> list[str]:
    return list(_exporters.keys())


def list_ingesters() -> list[str]:
    return list(_ingesters.keys())
