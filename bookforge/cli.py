"""BookForge CLI entry point.

Usage:
    bookforge convert input.html --output-dir ./out
    bookforge convert input.pdf --formats epub docx
    bookforge batch metadata.xlsx --input-dir ./files/
    bookforge serve
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import typer

app = typer.Typer(
    name="bookforge",
    help="Automated publishing pipeline: manuscripts to EPUB, DOCX, and PDF",
    no_args_is_help=True,
)


@app.command()
def convert(
    input_file: Path = typer.Argument(..., help="Input manuscript file"),
    output_dir: Path = typer.Option(Path("./output"), "--output-dir", "-o", help="Output directory"),
    formats: list[str] = typer.Option(["epub"], "--format", "-f", help="Output formats (epub, docx, pdf)"),
    template: str = typer.Option("academic", "--template", "-t", help="Template name"),
    rewrite: int = typer.Option(0, "--rewrite", "-r", help="Rewrite percentage (0 = no rewrite)"),
    title: str = typer.Option("", "--title", help="Book title (auto-generated if omitted)"),
    author: str = typer.Option("", "--author", help="Author name"),
):
    """Convert a single manuscript file to publication-ready output."""
    from bookforge.core.config import Config
    from bookforge.core.logging import configure_logging
    from bookforge.core.models import BookMetadata, JobConfig
    from bookforge.core.pipeline import Pipeline

    config = Config.load()
    configure_logging(
        level=config.get("logging.level", "INFO"),
        json_output=False,  # human-readable for CLI
    )

    metadata = BookMetadata(
        title=title or input_file.stem.replace("_", " ").replace("-", " ").title(),
        authors=[author] if author else [],
        publisher_name="Self-Published",
        year=2026,
    )
    job_config = JobConfig(
        template=template,
        rewrite_percent=rewrite,
        output_formats=formats,
        generate_title=not bool(title),
        generate_preface=False,
        generate_acknowledgement=False,
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    typer.echo(f"Converting: {input_file.name}")

    pipeline = Pipeline(config.as_dict())

    async def run():
        normalized = await pipeline.process_file(input_file, job_config)
        outputs = await pipeline.process_book([normalized], metadata, job_config)
        for path in outputs:
            dest = output_dir / path.name
            shutil.copy2(path, dest)
            typer.echo(f"  Written: {dest}")

    asyncio.run(run())
    typer.echo("Done.")


@app.command()
def batch(
    excel_file: Path = typer.Argument(..., help="Excel metadata file (.xlsx)"),
    input_dir: Path = typer.Option(Path("."), "--input-dir", "-i", help="Directory containing input manuscript files"),
    output_dir: Path = typer.Option(Path("./output"), "--output-dir", "-o", help="Output directory"),
    columns_config: Path = typer.Option(None, "--columns", "-c", help="Column mapping YAML (default: config/columns.yaml)"),
):
    """Batch-process books from an Excel metadata sheet.

    Each row in the Excel file defines one book. The pipeline reads metadata
    from the row (title, author, formats, etc.), locates input files in
    --input-dir, and runs the full pipeline per book.
    """
    from bookforge.core.config import Config
    from bookforge.core.exceptions import BookForgeError, MetadataError
    from bookforge.core.logging import configure_logging
    from bookforge.core.pipeline import Pipeline
    from bookforge.metadata.reader import load_columns_config, read_metadata
    from bookforge.metadata.validator import build_book_metadata, build_job_config

    config = Config.load()
    configure_logging(
        level=config.get("logging.level", "INFO"),
        json_output=False,
    )

    # Load column mapping
    col_map = load_columns_config(columns_config)

    # Read Excel
    typer.echo(f"Reading metadata: {excel_file.name}")
    rows = read_metadata(excel_file, col_map)
    typer.echo(f"  Found {len(rows)} book(s)")

    output_dir.mkdir(parents=True, exist_ok=True)
    pipeline = Pipeline(config.as_dict())

    succeeded = 0
    failed = 0

    for row_idx, row in enumerate(rows, start=1):
        row_title = row.get("title") or f"Book {row_idx}"
        typer.echo(f"\n[{row_idx}/{len(rows)}] {row_title}")

        # Validate metadata
        try:
            metadata = build_book_metadata(row)
            job_config = build_job_config(row)
        except MetadataError as exc:
            typer.echo(f"  SKIP — metadata error: {exc}", err=True)
            failed += 1
            continue

        # Resolve input files
        input_files_raw = row.get("input_files")
        if not input_files_raw:
            typer.echo("  SKIP — no input files specified", err=True)
            failed += 1
            continue

        from bookforge.metadata.validator import _parse_list_field
        file_names = _parse_list_field(str(input_files_raw))
        input_files: list[Path] = []
        missing = False
        for fname in file_names:
            fpath = input_dir / fname
            if not fpath.exists():
                typer.echo(f"  SKIP — input file not found: {fpath}", err=True)
                missing = True
                break
            input_files.append(fpath)

        if missing:
            failed += 1
            continue

        # Run pipeline
        try:
            book_output_dir = output_dir / _safe_dirname(row_title, row_idx)
            book_output_dir.mkdir(parents=True, exist_ok=True)

            outputs = asyncio.run(
                _run_book(pipeline, input_files, metadata, job_config)
            )

            for path in outputs:
                dest = book_output_dir / path.name
                shutil.copy2(path, dest)
                typer.echo(f"  Written: {dest}")

            succeeded += 1

        except BookForgeError as exc:
            typer.echo(f"  FAILED: {exc}", err=True)
            failed += 1
        except Exception as exc:
            typer.echo(f"  FAILED (unexpected): {exc}", err=True)
            failed += 1

    typer.echo(f"\nBatch complete: {succeeded} succeeded, {failed} failed out of {len(rows)}")
    if failed > 0:
        raise typer.Exit(code=1)


async def _run_book(pipeline, input_files, metadata, job_config):
    """Run the full pipeline for one book (multiple input files)."""
    # Stage 1+2: process each file
    normalized = []
    for fpath in input_files:
        nc = await pipeline.process_file(fpath, job_config)
        normalized.append(nc)

    # Stages 3-6: assemble, AI, structure, export
    return await pipeline.process_book(normalized, metadata, job_config)


def _safe_dirname(title: str, index: int) -> str:
    """Create a filesystem-safe directory name from a book title."""
    import re
    safe = re.sub(r"[^\w\s-]", "", title)
    safe = re.sub(r"[\s]+", "_", safe).strip("_")
    return f"{index:03d}_{safe[:50]}" if safe else f"{index:03d}_book"


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload"),
):
    """Start the BookForge web server."""
    import uvicorn
    uvicorn.run(
        "bookforge.main:app",
        host=host,
        port=port,
        reload=reload,
    )
