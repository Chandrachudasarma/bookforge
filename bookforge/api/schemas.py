"""Pydantic request/response schemas for the BookForge API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    """Full job information returned by GET /jobs/{id}."""

    job_id: str
    status: str
    input_files: list[str] = []
    metadata: dict = {}
    config: dict = {}
    progress: ProgressResponse | None = None
    file_results: list[FileResultResponse] = []
    created_at: str = ""
    completed_at: str | None = None


class ProgressResponse(BaseModel):
    """Live progress for a running job."""

    total_files: int = 0
    completed_files: int = 0
    current_file: str | None = None
    current_stage: str | None = None
    succeeded: int = 0
    failed: int = 0
    elapsed_seconds: float = 0.0


class FileResultResponse(BaseModel):
    """Result of processing a single file."""

    file_path: str
    status: str
    error: str | None = None
    output_paths: list[str] = []


class JobListItem(BaseModel):
    """Summary of a job for list views."""

    job_id: str
    status: str
    title: str = ""
    created_at: str = ""
    total_files: int = 0
    succeeded: int = 0
    failed: int = 0


class JobListResponse(BaseModel):
    """Response for GET /jobs."""

    jobs: list[JobListItem] = []
    total: int = 0


class CreateJobRequest(BaseModel):
    """Metadata and config sent alongside uploaded files."""

    title: str = ""
    author: str = ""
    template: str = "academic"
    rewrite_percent: int = 0
    output_formats: list[str] = Field(default_factory=lambda: ["epub"])
    generate_title: bool = True
    generate_preface: bool = False
    generate_acknowledgement: bool = False


class CreateJobResponse(BaseModel):
    """Response for POST /jobs."""

    job_id: str
    status: str
    message: str = "Job created"


# Rebuild forward refs for nested models
JobResponse.model_rebuild()
