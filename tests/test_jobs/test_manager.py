"""Tests for the job manager."""

from pathlib import Path

import pytest

from bookforge.core.models import BookMetadata, JobConfig
from bookforge.jobs.manager import JobManager
from bookforge.jobs.models import JobStatus
from bookforge.jobs.store import FileJobStore


@pytest.fixture
def store(tmp_path: Path) -> FileJobStore:
    return FileJobStore(tmp_path / "jobs")


@pytest.fixture
def manager(store) -> JobManager:
    return JobManager(store)


@pytest.fixture
def sample_metadata() -> BookMetadata:
    return BookMetadata(title="Test Book", authors=["Author"])


@pytest.fixture
def sample_config() -> JobConfig:
    return JobConfig(output_formats=["epub"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_create_job(manager, sample_metadata, sample_config, tmp_path):
    f1 = tmp_path / "ch1.html"
    f1.write_text("<p>content</p>")

    job = manager.create_job([f1], sample_metadata, sample_config)

    assert job.job_id  # non-empty
    assert job.status == JobStatus.QUEUED
    assert len(job.input_files) == 1
    assert job.metadata["title"] == "Test Book"


def test_created_job_is_persisted(manager, store, sample_metadata, sample_config, tmp_path):
    f1 = tmp_path / "ch1.html"
    f1.write_text("<p>content</p>")

    job = manager.create_job([f1], sample_metadata, sample_config)
    loaded = store.read_job(job.job_id)

    assert loaded is not None
    assert loaded.job_id == job.job_id


def test_get_job(manager, sample_metadata, sample_config, tmp_path):
    f1 = tmp_path / "ch1.html"
    f1.write_text("<p>content</p>")

    job = manager.create_job([f1], sample_metadata, sample_config)
    found = manager.get_job(job.job_id)

    assert found is not None
    assert found.job_id == job.job_id


def test_get_nonexistent_job(manager):
    assert manager.get_job("nonexistent") is None


def test_list_jobs(manager, sample_metadata, sample_config, tmp_path):
    f1 = tmp_path / "ch1.html"
    f1.write_text("<p>content</p>")

    manager.create_job([f1], sample_metadata, sample_config)
    manager.create_job([f1], sample_metadata, sample_config)

    jobs = manager.list_jobs()
    assert len(jobs) == 2


def test_cancel_job(manager, sample_metadata, sample_config, tmp_path):
    f1 = tmp_path / "ch1.html"
    f1.write_text("<p>content</p>")

    job = manager.create_job([f1], sample_metadata, sample_config)
    assert manager.cancel_job(job.job_id) is True

    loaded = manager.get_job(job.job_id)
    assert loaded.status == JobStatus.CANCELLED


def test_cancel_completed_job_fails(manager, store, sample_metadata, sample_config, tmp_path):
    f1 = tmp_path / "ch1.html"
    f1.write_text("<p>content</p>")

    job = manager.create_job([f1], sample_metadata, sample_config)
    store.update_job_status(job.job_id, JobStatus.COMPLETED)

    assert manager.cancel_job(job.job_id) is False


def test_cancel_nonexistent_returns_false(manager):
    assert manager.cancel_job("nonexistent") is False


def test_job_directories_created(manager, store, sample_metadata, sample_config, tmp_path):
    f1 = tmp_path / "ch1.html"
    f1.write_text("<p>content</p>")

    job = manager.create_job([f1], sample_metadata, sample_config)
    job_dir = store.get_job_dir(job.job_id)

    assert (job_dir / "input").is_dir()
    assert (job_dir / "output").is_dir()
