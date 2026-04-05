"""Tests for the FastAPI API routes.

Uses httpx TestClient — no real server, no subprocess workers.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from bookforge.api.routes import init_api, router, _get_manager
from bookforge.core.config import Config
from bookforge.core.models import BookMetadata, JobConfig
from bookforge.jobs.manager import JobManager
from bookforge.jobs.models import Job, JobProgress, JobStatus, FileResult
from bookforge.jobs.store import FileJobStore
from bookforge.main import app


@pytest.fixture
def store(tmp_path: Path) -> FileJobStore:
    return FileJobStore(tmp_path / "jobs")


@pytest.fixture
def manager(store) -> JobManager:
    return JobManager(store)


@pytest.fixture
def client(tmp_path, manager):
    """TestClient with API initialized against a temp store.

    The manager must be set AFTER entering the TestClient context, because
    TestClient triggers the FastAPI lifespan which calls init_api() and
    overwrites the global _manager.
    """
    import bookforge.api.routes as routes_mod

    with TestClient(app) as c:
        # Override AFTER lifespan runs (which sets _manager from real config)
        routes_mod._manager = manager
        routes_mod._config = Config({"worker": {"state_dir": str(tmp_path / "jobs")}})
        # Mock spawn_worker to prevent real subprocess launches in tests
        manager.spawn_worker = lambda job_id: None
        # Disable auth for tests by overriding the dependency
        from bookforge.api.auth import require_auth
        app.dependency_overrides[require_auth] = lambda: "test_user"
        yield c
        app.dependency_overrides.clear()


@pytest.fixture
def sample_html(tmp_path: Path) -> Path:
    f = tmp_path / "test.html"
    f.write_text("<h1>Hello</h1><p>Content</p>")
    return f


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "dependencies" in data


# ---------------------------------------------------------------------------
# Jobs — list (empty)
# ---------------------------------------------------------------------------


def test_list_jobs_empty(client):
    resp = client.get("/api/v1/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["jobs"] == []
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# Jobs — create
# ---------------------------------------------------------------------------


def test_create_job(client, sample_html):
    with open(sample_html, "rb") as f:
        resp = client.post(
            "/api/v1/jobs",
            files=[("files", ("test.html", f, "text/html"))],
            data={
                "metadata": '{"title": "Test Book", "author": "Jane"}',
                "config": '{"template": "academic", "output_formats": ["epub"]}',
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "queued"


def test_create_job_appears_in_list(client, sample_html):
    with open(sample_html, "rb") as f:
        client.post(
            "/api/v1/jobs",
            files=[("files", ("test.html", f, "text/html"))],
            data={"metadata": '{"title": "Listed Book"}', "config": "{}"},
        )

    resp = client.get("/api/v1/jobs")
    data = resp.json()
    assert data["total"] == 1
    assert data["jobs"][0]["status"] == "queued"


# ---------------------------------------------------------------------------
# Jobs — get by ID
# ---------------------------------------------------------------------------


def test_get_job_by_id(client, sample_html):
    with open(sample_html, "rb") as f:
        create_resp = client.post(
            "/api/v1/jobs",
            files=[("files", ("test.html", f, "text/html"))],
            data={"metadata": '{"title": "Detail Book"}', "config": "{}"},
        )
    job_id = create_resp.json()["job_id"]

    resp = client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == job_id
    assert len(data["input_files"]) == 1


def test_get_nonexistent_job_returns_404(client):
    resp = client.get("/api/v1/jobs/nonexistent123")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Jobs — download
# ---------------------------------------------------------------------------


def test_download_nonexistent_job_returns_404(client):
    resp = client.get("/api/v1/jobs/nonexistent/download/book.epub")
    assert resp.status_code == 404


def test_download_missing_file_returns_404(client, manager):
    job = manager.create_job([], BookMetadata(title="X"), JobConfig())
    resp = client.get(f"/api/v1/jobs/{job.job_id}/download/book.epub")
    assert resp.status_code == 404


def test_download_existing_file(client, manager, store):
    job = manager.create_job([], BookMetadata(title="X"), JobConfig())
    output_dir = store.get_job_dir(job.job_id) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "book.epub").write_bytes(b"fake epub content")

    resp = client.get(f"/api/v1/jobs/{job.job_id}/download/book.epub")
    assert resp.status_code == 200
    assert resp.content == b"fake epub content"


# ---------------------------------------------------------------------------
# Config endpoint
# ---------------------------------------------------------------------------


def test_config_endpoint_requires_auth(client):
    """Config endpoint is behind auth — returns 401 without credentials."""
    from bookforge.api.auth import require_auth
    # Temporarily restore real auth to test it
    app.dependency_overrides.pop(require_auth, None)
    import bookforge.api.auth as auth_mod
    auth_mod._password = "testpass"
    resp = client.get("/api/v1/config")
    assert resp.status_code == 401
    # Restore override for other tests
    auth_mod._password = ""
    app.dependency_overrides[require_auth] = lambda: "test_user"


# ---------------------------------------------------------------------------
# Invalid request handling
# ---------------------------------------------------------------------------


def test_create_job_invalid_metadata_json(client, sample_html):
    with open(sample_html, "rb") as f:
        resp = client.post(
            "/api/v1/jobs",
            files=[("files", ("test.html", f, "text/html"))],
            data={"metadata": "not json", "config": "{}"},
        )
    assert resp.status_code == 400


def test_download_path_traversal_blocked(client, manager, store):
    """Ensure path traversal in filename is blocked."""
    job = manager.create_job([], BookMetadata(title="X"), JobConfig())
    output_dir = store.get_job_dir(job.job_id) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    resp = client.get(f"/api/v1/jobs/{job.job_id}/download/../../job.json")
    assert resp.status_code in (403, 404)
