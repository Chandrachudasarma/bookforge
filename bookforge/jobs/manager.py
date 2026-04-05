"""Job manager — creates jobs and spawns worker subprocesses.

Bridges the API/CLI to the store and worker. The manager is stateless —
all persistent state lives in the FileJobStore.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from bookforge.core.logging import get_logger
from bookforge.core.models import BookMetadata, JobConfig
from bookforge.jobs.models import FileResult, Job, JobProgress, JobStatus
from bookforge.jobs.store import FileJobStore

logger = get_logger("jobs.manager")


class JobManager:
    """Creates and manages conversion jobs."""

    def __init__(self, store: FileJobStore):
        self._store = store

    def create_job(
        self,
        input_files: list[Path],
        metadata: BookMetadata,
        job_config: JobConfig,
    ) -> Job:
        """Create a new job and persist it to the store.

        Does NOT spawn the worker — call spawn_worker() separately,
        or use submit_job() for create+spawn in one call.
        """
        job_id = uuid4().hex[:12]

        # Create job directories
        job_dir = self._store.get_job_dir(job_id)
        (job_dir / "input").mkdir(parents=True, exist_ok=True)
        (job_dir / "output").mkdir(parents=True, exist_ok=True)

        job = Job(
            job_id=job_id,
            status=JobStatus.QUEUED,
            input_files=[str(f) for f in input_files],
            metadata=asdict(metadata),
            config=asdict(job_config),
            progress=JobProgress(total_files=len(input_files)),
            file_results=[],
            created_at=datetime.now(timezone.utc).isoformat(),
            output_dir=str(job_dir / "output"),
        )

        self._store.write_job(job)
        logger.info("Job created", job_id=job_id, files=len(input_files))
        return job

    def submit_job(
        self,
        input_files: list[Path],
        metadata: BookMetadata,
        job_config: JobConfig,
    ) -> Job:
        """Create a job and immediately spawn a worker for it."""
        job = self.create_job(input_files, metadata, job_config)
        self.spawn_worker(job.job_id)
        return job

    def spawn_worker(self, job_id: str) -> None:
        """Spawn a subprocess worker for the given job.

        start_new_session=True detaches the worker from the parent's process
        group so it survives API server restarts and Ctrl+C.
        """
        log_path = self._store.get_job_dir(job_id) / "worker.log"
        log_file = open(log_path, "w")
        subprocess.Popen(
            [
                sys.executable, "-m", "bookforge.jobs.worker",
                job_id, str(self._store.base_dir.resolve()),
            ],
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
        logger.info("Worker spawned", job_id=job_id)

    def get_job(self, job_id: str) -> Job | None:
        """Get a job by ID."""
        return self._store.read_job(job_id)

    def get_job_dir(self, job_id: str) -> Path:
        """Return the directory path for a job."""
        return self._store.get_job_dir(job_id)

    def get_progress(self, job_id: str) -> JobProgress | None:
        """Get live progress for a job."""
        return self._store.read_status(job_id)

    def get_results(self, job_id: str) -> list[FileResult]:
        """Get file results for a job."""
        return self._store.read_file_results(job_id)

    def list_jobs(self) -> list[Job]:
        """List all jobs (most recent first)."""
        jobs = []
        for job_id in self._store.list_jobs():
            job = self._store.read_job(job_id)
            if job:
                jobs.append(job)
        # Sort by created_at descending
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs

    def cancel_job(self, job_id: str) -> bool:
        """Mark a job as cancelled. Does not kill the worker process."""
        job = self._store.read_job(job_id)
        if job is None:
            return False
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            return False
        self._store.update_job_status(job_id, JobStatus.CANCELLED)
        logger.info("Job cancelled", job_id=job_id)
        return True
