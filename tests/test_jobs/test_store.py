"""Tests for the file-based job store."""

from pathlib import Path

import pytest

from bookforge.jobs.models import FileResult, Job, JobProgress, JobStatus
from bookforge.jobs.store import FileJobStore


@pytest.fixture
def store(tmp_path: Path) -> FileJobStore:
    return FileJobStore(tmp_path / "jobs")


@pytest.fixture
def sample_job() -> Job:
    return Job(
        job_id="test123",
        status=JobStatus.QUEUED,
        input_files=["chapter1.html", "chapter2.html"],
        metadata={"title": "Test Book", "authors": ["Author"]},
        config={"template": "academic", "output_formats": ["epub"]},
        progress=JobProgress(total_files=2),
        file_results=[],
        created_at="2026-04-05T12:00:00Z",
        output_dir="/tmp/output",
    )


# ---------------------------------------------------------------------------
# Write + read round-trips
# ---------------------------------------------------------------------------


def test_write_and_read_job(store, sample_job):
    store.write_job(sample_job)
    loaded = store.read_job("test123")

    assert loaded is not None
    assert loaded.job_id == "test123"
    assert loaded.status == JobStatus.QUEUED
    assert loaded.input_files == ["chapter1.html", "chapter2.html"]
    assert loaded.metadata["title"] == "Test Book"


def test_write_and_read_status(store, sample_job):
    store.write_job(sample_job)

    progress = JobProgress(
        total_files=2,
        completed_files=1,
        current_file="chapter2.html",
        current_stage="ingesting",
        succeeded=1,
        failed=0,
        elapsed_seconds=5.2,
    )
    store.write_status("test123", progress)

    loaded = store.read_status("test123")
    assert loaded is not None
    assert loaded.completed_files == 1
    assert loaded.current_file == "chapter2.html"
    assert loaded.elapsed_seconds == 5.2


def test_write_and_read_file_results(store, sample_job):
    store.write_job(sample_job)

    store.write_file_result("test123", FileResult(
        file_path="chapter1.html", status="success",
    ))
    store.write_file_result("test123", FileResult(
        file_path="chapter2.html", status="failed", error="OCR failed",
    ))

    results = store.read_file_results("test123")
    assert len(results) == 2
    assert results[0].file_path == "chapter1.html"
    assert results[0].status == "success"
    assert results[1].status == "failed"
    assert results[1].error == "OCR failed"


def test_update_job_status(store, sample_job):
    store.write_job(sample_job)
    store.update_job_status("test123", JobStatus.PROCESSING)

    loaded = store.read_job("test123")
    assert loaded.status == JobStatus.PROCESSING


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_read_nonexistent_job(store):
    assert store.read_job("nonexistent") is None


def test_read_nonexistent_status(store):
    assert store.read_status("nonexistent") is None


def test_read_nonexistent_results(store):
    assert store.read_file_results("nonexistent") == []


def test_list_jobs_empty(store):
    assert store.list_jobs() == []


def test_list_jobs_returns_ids(store, sample_job):
    store.write_job(sample_job)

    job2 = Job(
        job_id="other456",
        status=JobStatus.COMPLETED,
        input_files=[],
        metadata={},
        config={},
        created_at="2026-04-05T13:00:00Z",
        output_dir="",
    )
    store.write_job(job2)

    ids = store.list_jobs()
    assert "test123" in ids
    assert "other456" in ids


def test_get_job_dir(store):
    d = store.get_job_dir("abc")
    assert d == store.base_dir / "abc"
