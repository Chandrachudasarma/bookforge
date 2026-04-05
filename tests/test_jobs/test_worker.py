"""Tests for the subprocess worker.

Runs run_job() directly (not as subprocess) to verify:
  - Output files are produced and copied to job output dir
  - Job metadata round-trips without crashing
  - Failed files set job status to FAILED
"""

import asyncio
from dataclasses import asdict
from pathlib import Path

import pytest

from bookforge.core.config import Config
from bookforge.core.models import BookMetadata, JobConfig
from bookforge.jobs.models import Job, JobProgress, JobStatus
from bookforge.jobs.store import FileJobStore
from bookforge.jobs.worker import run_job


@pytest.fixture
def store(tmp_path: Path) -> FileJobStore:
    return FileJobStore(tmp_path / "jobs")


@pytest.fixture
def config(tmp_path: Path) -> dict:
    """Pipeline config with AI disabled and temp dir set."""
    return {
        "pipeline": {"temp_dir": str(tmp_path / "temp")},
        "ai": {"provider": "anthropic", "api_key": ""},
    }


def _make_job(store: FileJobStore, input_files: list[Path], **meta_overrides) -> Job:
    """Create and persist a job for testing."""
    meta = {"title": "Test Book", "authors": ["Author"], "publisher_name": "Pub",
            "year": 2026, "language": "en", "isbn": None, "eisbn": None,
            "publisher_address": None, "publisher_email": None, "cover_image": None,
            "chapter_order": {}, "source_row_indices": {}}
    meta.update(meta_overrides)

    config = asdict(JobConfig(
        output_formats=["epub"],
        generate_title=False,
        generate_preface=False,
        generate_acknowledgement=False,
        rewrite_percent=0,
    ))

    job = Job(
        job_id="test_worker_job",
        status=JobStatus.QUEUED,
        input_files=[str(f) for f in input_files],
        metadata=meta,
        config=config,
        progress=JobProgress(total_files=len(input_files)),
        created_at="2026-04-05T12:00:00Z",
        output_dir=str(store.get_job_dir("test_worker_job") / "output"),
    )
    (store.get_job_dir(job.job_id) / "input").mkdir(parents=True, exist_ok=True)
    (store.get_job_dir(job.job_id) / "output").mkdir(parents=True, exist_ok=True)
    store.write_job(job)
    return job


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_worker_produces_output_files(store, config, tmp_path):
    """Worker should produce an EPUB in the job's output directory."""
    html_file = tmp_path / "chapter.html"
    html_file.write_text("<h1>Chapter 1</h1><p>Content of chapter one.</p>")

    job = _make_job(store, [html_file])
    asyncio.run(run_job(job, store, config))

    # Check output directory has the EPUB
    output_dir = store.get_job_dir(job.job_id) / "output"
    epub_files = list(output_dir.glob("*.epub"))
    assert len(epub_files) >= 1, f"Expected EPUB in {output_dir}, found: {list(output_dir.iterdir())}"
    assert epub_files[0].stat().st_size > 0

    # Check results.json has the output path
    results = store.read_file_results(job.job_id)
    book_results = [r for r in results if r.file_path == "book"]
    assert len(book_results) == 1
    assert len(book_results[0].output_paths) >= 1

    # Check final status
    final_job = store.read_job(job.job_id)
    assert final_job.status == JobStatus.COMPLETED


def test_worker_metadata_round_trip(store, config, tmp_path):
    """BookMetadata(**job.metadata) must work after worker finishes."""
    html_file = tmp_path / "chapter.html"
    html_file.write_text("<h1>Test</h1><p>Content.</p>")

    job = _make_job(store, [html_file])
    asyncio.run(run_job(job, store, config))

    # Re-read the job and verify metadata can be deserialized
    final_job = store.read_job(job.job_id)
    meta = BookMetadata(**final_job.metadata)
    assert meta.title == "Test Book"
    assert meta.authors == ["Author"]


def test_worker_failure_sets_failed_status(store, config, tmp_path):
    """Worker given an invalid file should set status to FAILED."""
    bad_file = tmp_path / "nonexistent.html"
    # Don't create the file — it doesn't exist

    job = _make_job(store, [bad_file])
    asyncio.run(run_job(job, store, config))

    final_job = store.read_job(job.job_id)
    assert final_job.status == JobStatus.FAILED

    # Status should show failed
    progress = store.read_status(job.job_id)
    assert progress.current_stage == "failed"
