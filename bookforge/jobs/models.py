"""Job infrastructure data models.

Job state is fully serializable to JSON for the file-based store.
The API reads status.json for polling; the worker writes it after each file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class JobStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobProgress:
    """Live progress — written by worker, read by API for polling."""

    total_files: int = 0
    completed_files: int = 0
    current_file: str | None = None
    current_stage: str | None = None
    succeeded: int = 0
    failed: int = 0
    elapsed_seconds: float = 0.0


@dataclass
class FileResult:
    """Result of processing a single input file."""

    file_path: str  # stored as string for JSON serialization
    status: str  # "success" | "failed" | "skipped"
    error: str | None = None
    output_paths: list[str] = field(default_factory=list)


@dataclass
class Job:
    """Full job definition — persisted to data/jobs/{job_id}/job.json."""

    job_id: str
    status: JobStatus
    input_files: list[str]  # stored as strings for JSON serialization
    metadata: dict  # BookMetadata as dict
    config: dict  # JobConfig as dict
    progress: JobProgress = field(default_factory=JobProgress)
    file_results: list[FileResult] = field(default_factory=list)
    created_at: str = ""  # ISO format string
    completed_at: str | None = None
    output_dir: str = ""
