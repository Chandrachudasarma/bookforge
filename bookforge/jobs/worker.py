"""Subprocess worker — runs a job's pipeline in an isolated process.

Entry point:
    python -m bookforge.jobs.worker <job_id> <data_dir>

The worker:
  1. Reads the Job from the file store
  2. Stages 1+2: processes each file concurrently (semaphore-bounded)
  3. Stages 3-6: assembles, AI-processes, structures, and exports the book
  4. Writes progress after each file and on completion

start_new_session=True in the spawner (manager.py) ensures this process
survives API server restarts and Ctrl+C.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import time
from dataclasses import asdict
from pathlib import Path

from bookforge.core.config import Config
from bookforge.core.exceptions import BookForgeError
from bookforge.core.logging import configure_logging, get_logger
from bookforge.core.models import BookMetadata, JobConfig, NormalizedContent
from bookforge.core.pipeline import Pipeline
from bookforge.jobs.models import FileResult, Job, JobProgress, JobStatus
from bookforge.jobs.store import FileJobStore

logger = get_logger("jobs.worker")


async def run_job(job: Job, store: FileJobStore, config: dict) -> None:
    """Execute the full pipeline for a job."""
    start_time = time.monotonic()

    # Reconstruct typed models from the serialized dicts
    metadata = BookMetadata(**job.metadata)
    job_config = JobConfig(**job.config)
    pipeline = Pipeline(config)

    total_files = len(job.input_files)
    semaphore = asyncio.Semaphore(job_config.max_concurrent_files)

    # Update status to processing
    store.update_job_status(job.job_id, JobStatus.PROCESSING)
    _write_progress(store, job.job_id, start_time, total_files, 0, 0, 0, None, "starting")

    # ------------------------------------------------------------------
    # Stages 1+2: per-file (concurrent, semaphore-bounded)
    # ------------------------------------------------------------------
    normalized_contents: list[NormalizedContent] = []
    succeeded = 0
    failed_count = 0

    async def process_one_file(file_path_str: str) -> NormalizedContent | None:
        nonlocal succeeded, failed_count
        file_path = Path(file_path_str)

        # Check for cancellation before each file
        current_job = store.read_job(job.job_id)
        if current_job and current_job.status == JobStatus.CANCELLED:
            logger.info("Job cancelled, skipping file", file=file_path.name)
            return None

        async with semaphore:
            _write_progress(
                store, job.job_id, start_time, total_files,
                succeeded + failed_count, succeeded, failed_count,
                file_path.name, "ingesting",
            )
            try:
                normalized = await pipeline.process_file(file_path, job_config)
                succeeded += 1
                store.write_file_result(job.job_id, FileResult(
                    file_path=str(file_path),
                    status="success",
                ))
                return normalized
            except BookForgeError as exc:
                failed_count += 1
                logger.error("File processing failed", file=file_path.name, error=str(exc))
                store.write_file_result(job.job_id, FileResult(
                    file_path=str(file_path),
                    status="failed",
                    error=str(exc),
                ))
                return None

    results = await asyncio.gather(
        *[process_one_file(f) for f in job.input_files],
        return_exceptions=True,
    )
    normalized_contents = [r for r in results if isinstance(r, NormalizedContent)]

    if not normalized_contents:
        _write_progress(
            store, job.job_id, start_time, total_files,
            total_files, 0, total_files, None, "failed",
        )
        store.update_job_status(job.job_id, JobStatus.FAILED)
        logger.error("All files failed — no content to assemble", job_id=job.job_id)
        return

    # Check for cancellation before book processing
    current_job = store.read_job(job.job_id)
    if current_job and current_job.status == JobStatus.CANCELLED:
        logger.info("Job cancelled before assembly", job_id=job.job_id)
        return

    # ------------------------------------------------------------------
    # Stages 3-6: per-book (sequential)
    # ------------------------------------------------------------------
    _write_progress(
        store, job.job_id, start_time, total_files,
        total_files, succeeded, failed_count, None, "assembling",
    )

    try:
        output_paths = await pipeline.process_book(
            normalized_contents, metadata, job_config,
        )

        # Save AI output to job directory for debugging and API access
        import json as _json
        ai_output_src = Path(pipeline._config.get("pipeline", {}).get("temp_dir", "/tmp/bookforge")) / "last_ai_output.json"
        if ai_output_src.exists():
            ai_dest = store.get_job_dir(job.job_id) / "ai_output.json"
            shutil.copy2(ai_output_src, ai_dest)
            # Also write generated.json for the API title display
            try:
                ai_data = _json.loads(ai_dest.read_text())
                if ai_data.get("generated_title"):
                    (store.get_job_dir(job.job_id) / "generated.json").write_text(
                        _json.dumps({"title": ai_data["generated_title"]})
                    )
            except Exception:
                pass

        # Copy outputs to the job's output directory
        output_dir = store.get_job_dir(job.job_id) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        final_paths: list[str] = []
        for path in output_paths:
            dest = output_dir / path.name
            shutil.copy2(path, dest)
            final_paths.append(str(dest))
            logger.debug("Output copied", src=str(path), dest=str(dest))

        store.write_file_result(job.job_id, FileResult(
            file_path="book",
            status="success" if final_paths else "failed",
            output_paths=final_paths,
            error="No output files produced" if not final_paths else None,
        ))

        # Final status — FAILED if zero outputs even when ingestion succeeded
        if not final_paths:
            final_status = JobStatus.FAILED
        elif failed_count == 0:
            final_status = JobStatus.COMPLETED
        else:
            final_status = JobStatus.PARTIALLY_FAILED
        store.update_job_status(job.job_id, final_status)
        _write_progress(
            store, job.job_id, start_time, total_files,
            total_files, succeeded, failed_count, None, "completed",
        )
        logger.info(
            "Job completed",
            job_id=job.job_id,
            succeeded=succeeded,
            failed=failed_count,
            outputs=len(final_paths),
        )

    except BookForgeError as exc:
        logger.error("Book processing failed", job_id=job.job_id, error=str(exc))
        store.write_file_result(job.job_id, FileResult(
            file_path="book",
            status="failed",
            error=str(exc),
        ))
        store.update_job_status(job.job_id, JobStatus.FAILED)
        _write_progress(
            store, job.job_id, start_time, total_files,
            total_files, succeeded, failed_count, None, "failed",
        )


def _write_progress(
    store: FileJobStore,
    job_id: str,
    start_time: float,
    total: int,
    completed: int,
    succeeded: int,
    failed: int,
    current_file: str | None,
    current_stage: str,
) -> None:
    store.write_status(job_id, JobProgress(
        total_files=total,
        completed_files=completed,
        current_file=current_file,
        current_stage=current_stage,
        succeeded=succeeded,
        failed=failed,
        elapsed_seconds=round(time.monotonic() - start_time, 2),
    ))


# ---------------------------------------------------------------------------
# Subprocess entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point when run as: python -m bookforge.jobs.worker <job_id> <data_dir>"""
    if len(sys.argv) < 3:
        print("Usage: python -m bookforge.jobs.worker <job_id> <data_dir>", file=sys.stderr)
        sys.exit(1)

    job_id = sys.argv[1]
    data_dir = Path(sys.argv[2])

    config = Config.load()
    configure_logging(
        level=config.get("logging.level", "INFO"),
        json_output=True,
    )

    store = FileJobStore(data_dir)
    job = store.read_job(job_id)

    if job is None:
        logger.error("Job not found", job_id=job_id)
        sys.exit(1)

    logger.info("Worker starting", job_id=job_id, files=len(job.input_files))
    try:
        asyncio.run(run_job(job, store, config.as_dict()))
    except Exception as exc:
        logger.error("Worker crashed", job_id=job_id, error=str(exc), exc_info=True)
        store.update_job_status(job_id, JobStatus.FAILED)
        store.write_status(job_id, JobProgress(
            total_files=len(job.input_files),
            current_stage="failed",
            elapsed_seconds=0,
        ))
        store.write_file_result(job_id, FileResult(
            file_path="worker",
            status="failed",
            error=str(exc),
        ))


if __name__ == "__main__":
    main()
