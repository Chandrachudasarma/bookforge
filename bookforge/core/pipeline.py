"""Pipeline Orchestrator — wires all 6 stages together.

Stage boundary:
  Stages 1+2: per-file (parallel)  → process_file()
  Stages 3-6: per-book (sequential) → process_book()

The worker calls process_file() for each file concurrently (semaphore-
bounded), collects NormalizedContent results, then calls process_book()
once with the full list.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from bookforge.ai import stage as ai_stage
from bookforge.assembly.assembler import assemble
from bookforge.core.exceptions import AIError, BookForgeError, ExportError
from bookforge.core.logging import get_logger
from bookforge.core.models import (
    BookMetadata,
    JobConfig,
    NormalizedContent,
    ProcessedContent,
)
from bookforge.core import registry
from bookforge.ingestion.detector import detect_format
from bookforge.normalization.normalizer import Normalizer
from bookforge.structure.builder import build_manifest

logger = get_logger("pipeline")


class Pipeline:
    """Orchestrates the 6-stage BookForge pipeline."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}

    # ------------------------------------------------------------------
    # Stage 1+2: per-file
    # ------------------------------------------------------------------

    async def process_file(
        self,
        file_path: Path,
        job_config: JobConfig,
    ) -> NormalizedContent:
        """Ingest (Stage 1) and Normalize (Stage 2) a single file.

        Runs in a thread executor so blocking I/O doesn't stall the event loop.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._process_file_sync,
            file_path,
            job_config,
        )

    def _process_file_sync(
        self,
        file_path: Path,
        job_config: JobConfig,
    ) -> NormalizedContent:
        config_dict = self._config

        # Stage 1: Ingest
        ingester = registry.get_ingester_for_file(file_path)
        raw = ingester.ingest(file_path, config_dict)
        logger.debug("File ingested", file=file_path.name, format=raw.format_hint)

        # Stage 2: Normalize
        normalizer = Normalizer(config_dict)
        normalized = normalizer.normalize(raw)
        logger.debug(
            "File normalized",
            file=file_path.name,
            headings=len(normalized.detected_headings),
            protected_blocks=len(normalized.protected_blocks),
        )

        return normalized

    # ------------------------------------------------------------------
    # Stages 3-6: per-book
    # ------------------------------------------------------------------

    async def process_book(
        self,
        normalized_contents: list[NormalizedContent],
        metadata: BookMetadata,
        job_config: JobConfig,
    ) -> list[Path]:
        """Assemble, AI-process, structure, and export the book.

        Returns a list of output file paths (one per requested format).
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._process_book_sync,
            normalized_contents,
            metadata,
            job_config,
        )

    def _process_book_sync(
        self,
        normalized_contents: list[NormalizedContent],
        metadata: BookMetadata,
        job_config: JobConfig,
    ) -> list[Path]:
        # Stage 3: Assemble
        logger.debug("Assembling book", article_count=len(normalized_contents))
        assembled = assemble(normalized_contents, metadata)

        # Stage 4: AI Processing
        processed = self._ai_stage(assembled, metadata, job_config)

        # Expose generated title for the worker to persist
        self._generated_title = processed.generated_title

        # Save AI output to disk for debugging and re-runs without API calls
        import json as _json
        ai_output_dir = Path(self._config.get("pipeline", {}).get("temp_dir", "/tmp/bookforge"))
        ai_output_dir.mkdir(parents=True, exist_ok=True)
        try:
            ai_output_path = ai_output_dir / "last_ai_output.json"
            ai_output_path.write_text(_json.dumps({
                "generated_title": processed.generated_title,
                "generated_preface": processed.generated_preface,
                "generated_acknowledgement": processed.generated_acknowledgement,
                "rewritten_body_html": processed.body_html,
                "ai_metadata": processed.ai_metadata,
            }, indent=2, default=str), encoding="utf-8")
            logger.debug("AI output saved", path=str(ai_output_path))
        except Exception:
            pass  # non-critical

        # If AI generated a title, update metadata so downstream stages use it
        if processed.generated_title:
            metadata = BookMetadata(
                title=processed.generated_title,
                authors=metadata.authors,
                isbn=metadata.isbn,
                eisbn=metadata.eisbn,
                publisher_name=metadata.publisher_name,
                publisher_address=metadata.publisher_address,
                publisher_email=metadata.publisher_email,
                year=metadata.year,
                language=metadata.language,
                cover_image=metadata.cover_image,
                chapter_order=metadata.chapter_order,
                source_row_indices=metadata.source_row_indices,
            )

        # Load template (Phase H)
        template = self._load_template(job_config.template)

        # Stage 5: Structure
        manifest = build_manifest(
            content=processed,
            metadata=metadata,
            config=job_config,
            template=template,
        )
        logger.debug("Manifest built", sections=len(manifest.sections))

        # Stage 6: Export — use a unique output directory per call to avoid
        # path collisions when multiple jobs run concurrently
        import uuid
        temp_dir = Path(self._config.get("pipeline", {}).get("temp_dir", "/tmp/bookforge"))
        output_dir = temp_dir / "output" / uuid.uuid4().hex[:8]
        output_dir.mkdir(parents=True, exist_ok=True)

        output_paths: list[Path] = []
        for fmt in job_config.output_formats:
            try:
                exporter = registry.get_exporter(fmt)
                out_path = output_dir / f"book.{fmt}"
                result = exporter.export(manifest, template=template, output_path=out_path)
                if result.success:
                    output_paths.append(result.output_path)
                    logger.debug("Export complete", format=fmt, path=str(result.output_path))
                else:
                    logger.warning("Export failed", format=fmt, error=result.error)
            except ExportError as exc:
                logger.warning("Export error", format=fmt, error=str(exc))

        return output_paths

    # ------------------------------------------------------------------
    # Internal: template loading
    # ------------------------------------------------------------------

    def _load_template(self, template_name: str):
        """Load the named template, or return None if loading fails.

        Template loading is best-effort — if the template is missing or
        invalid, the pipeline continues without it (exporters use fallback CSS).
        """
        try:
            from bookforge.templates.loader import load_template

            templates_dir_str = self._config.get("templates", {}).get("directory")
            templates_dir = Path(templates_dir_str) if templates_dir_str else None
            template = load_template(template_name, templates_dir)
            logger.debug("Template loaded", template=template_name)
            return template
        except Exception as exc:
            logger.warning(
                "Template loading failed — using defaults",
                template=template_name,
                error=str(exc),
            )
            return None

    # ------------------------------------------------------------------
    # Internal: AI stage
    # ------------------------------------------------------------------

    def _ai_stage(
        self,
        assembled,
        metadata: BookMetadata,
        job_config: JobConfig,
    ) -> ProcessedContent:
        """Run Stage 4: AI processing (generators + rewriter).

        If an AI provider is configured and any AI features are enabled,
        delegates to ai.stage.process(). Otherwise passes content through
        unchanged (no-op).
        """
        # Check if any AI work is actually needed
        needs_ai = (
            job_config.generate_title
            or job_config.generate_preface
            or job_config.generate_acknowledgement
            or job_config.rewrite_percent != 0
        )

        if not needs_ai:
            logger.debug("AI stage skipped — all features disabled")
            return ProcessedContent(
                body_html=assembled.body_html,
                generated_title=None,
                generated_preface=None,
                generated_acknowledgement=None,
                ai_metadata={"skipped": True},
                chapter_headings=assembled.chapter_headings,
                assets=assembled.assets,
            )

        # Resolve AI provider from config
        ai_config = self._config.get("ai", {})
        provider_name = ai_config.get("provider", "anthropic")

        try:
            provider = registry.get_ai_provider(provider_name, self._config)
        except Exception as exc:
            raise AIError(
                f"Cannot initialize AI provider '{provider_name}': {exc}"
            ) from exc

        return ai_stage.process(
            assembled=assembled,
            metadata=metadata,
            job_config=job_config,
            ai_provider=provider,
            config=self._config,
        )


# ---------------------------------------------------------------------------
# Module-level import trigger — ensure all plugins are registered
# ---------------------------------------------------------------------------

def _import_plugins() -> None:
    """Import all plugin modules so their @register_* decorators fire."""
    # Ingesters (Stage 1)
    import bookforge.ingestion.html_ingester      # noqa: F401
    import bookforge.ingestion.markdown_ingester   # noqa: F401
    import bookforge.ingestion.txt_ingester        # noqa: F401
    import bookforge.ingestion.docx_ingester       # noqa: F401
    import bookforge.ingestion.pdf_ingester        # noqa: F401
    import bookforge.ingestion.epub_ingester       # noqa: F401
    import bookforge.ingestion.ocr_ingester        # noqa: F401
    # OCR engines
    import bookforge.ingestion.ocr.tesseract       # noqa: F401
    # AI providers (Stage 4)
    import bookforge.ai.anthropic_provider         # noqa: F401
    import bookforge.ai.openai_provider            # noqa: F401
    # Exporters (Stage 6)
    import bookforge.export.epub_exporter          # noqa: F401
    import bookforge.export.docx_exporter          # noqa: F401
    import bookforge.export.pdf_exporter           # noqa: F401


_import_plugins()
