"""File-based job store.

All job state lives on disk at data/jobs/{job_id}/. No in-memory state,
no database. The API reads status.json for polling; the worker writes it.

Directory layout per job:
  data/jobs/{job_id}/
    job.json        — full Job definition (written once at creation)
    status.json     — JobProgress (written by worker after each file)
    results.json    — list of FileResult (appended by worker)
    input/          — uploaded input files (for API jobs)
    output/         — output files
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from bookforge.core.logging import get_logger
from bookforge.jobs.models import FileResult, Job, JobProgress, JobStatus

logger = get_logger("jobs.store")


class FileJobStore:
    """Persists job state to the filesystem."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write operations (called by manager and worker)
    # ------------------------------------------------------------------

    def write_job(self, job: Job) -> None:
        """Persist the full job definition."""
        job_dir = self._job_dir(job.job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "job.json").write_text(
            json.dumps(asdict(job), default=str, indent=2),
            encoding="utf-8",
        )

    def write_status(self, job_id: str, progress: JobProgress) -> None:
        """Update the live progress file (called by worker after each file)."""
        status_path = self._job_dir(job_id) / "status.json"
        status_path.write_text(
            json.dumps(asdict(progress), default=str, indent=2),
            encoding="utf-8",
        )

    def write_file_result(self, job_id: str, result: FileResult) -> None:
        """Append a file result to results.json."""
        results_path = self._job_dir(job_id) / "results.json"

        existing: list[dict] = []
        if results_path.exists():
            try:
                existing = json.loads(results_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                existing = []

        existing.append(asdict(result))
        results_path.write_text(
            json.dumps(existing, default=str, indent=2),
            encoding="utf-8",
        )

    def update_job_status(self, job_id: str, status: JobStatus) -> None:
        """Update just the status field in job.json."""
        job = self.read_job(job_id)
        if job:
            job.status = status
            self.write_job(job)

    # ------------------------------------------------------------------
    # Read operations (called by API and manager)
    # ------------------------------------------------------------------

    def read_job(self, job_id: str) -> Job | None:
        """Read the full job definition."""
        job_path = self._job_dir(job_id) / "job.json"
        if not job_path.exists():
            return None

        try:
            data = json.loads(job_path.read_text(encoding="utf-8"))
            data["status"] = JobStatus(data["status"])
            data["progress"] = JobProgress(**data.get("progress", {}))
            data["file_results"] = [
                FileResult(**r) for r in data.get("file_results", [])
            ]
            return Job(**data)
        except Exception as exc:
            logger.warning("Cannot read job", job_id=job_id, error=str(exc))
            return None

    def read_status(self, job_id: str) -> JobProgress | None:
        """Read the live progress for a job."""
        status_path = self._job_dir(job_id) / "status.json"
        if not status_path.exists():
            return None
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
            return JobProgress(**data)
        except Exception:
            return None

    def read_file_results(self, job_id: str) -> list[FileResult]:
        """Read all file results for a job."""
        results_path = self._job_dir(job_id) / "results.json"
        if not results_path.exists():
            return []
        try:
            data = json.loads(results_path.read_text(encoding="utf-8"))
            return [FileResult(**r) for r in data]
        except Exception:
            return []

    def list_jobs(self) -> list[str]:
        """Return all job IDs (directories containing job.json)."""
        if not self.base_dir.exists():
            return []
        return sorted(
            d.name
            for d in self.base_dir.iterdir()
            if d.is_dir() and (d / "job.json").exists()
        )

    def get_job_dir(self, job_id: str) -> Path:
        """Return the directory path for a job."""
        return self._job_dir(job_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _job_dir(self, job_id: str) -> Path:
        return self.base_dir / job_id
