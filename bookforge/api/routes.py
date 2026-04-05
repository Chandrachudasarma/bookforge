"""FastAPI routes for the BookForge REST API.

Endpoints:
  POST   /api/v1/jobs              — create a conversion job (upload files)
  GET    /api/v1/jobs              — list all jobs
  GET    /api/v1/jobs/{id}         — get job status and progress
  GET    /api/v1/jobs/{id}/download/{filename} — download an output file
  POST   /api/v1/batches           — create batch from Excel metadata
  GET    /api/v1/config            — get current pipeline config summary
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from bookforge.api.auth import require_auth

from bookforge.api.schemas import (
    CreateJobRequest,
    CreateJobResponse,
    FileResultResponse,
    JobListItem,
    JobListResponse,
    JobResponse,
    ProgressResponse,
)
from bookforge.core.config import Config
from bookforge.core.models import BookMetadata, JobConfig
from bookforge.jobs.manager import JobManager
from bookforge.jobs.models import JobStatus
from bookforge.jobs.store import FileJobStore

router = APIRouter()

# ---------------------------------------------------------------------------
# Shared state — initialized once when the router is included
# ---------------------------------------------------------------------------

_config: Config | None = None
_manager: JobManager | None = None


def init_api(config: Config) -> None:
    """Initialize the API with the application config. Called at startup."""
    global _config, _manager
    _config = config
    data_dir = Path(config.get("worker.state_dir", "data/jobs"))
    store = FileJobStore(data_dir)
    _manager = JobManager(store)


def _get_manager() -> JobManager:
    if _manager is None:
        # Lazy init for tests or if init_api wasn't called
        config = Config.load()
        init_api(config)
    return _manager


# ---------------------------------------------------------------------------
# Jobs endpoints
# ---------------------------------------------------------------------------


_MAX_JOBS_PER_USER = 3


@router.post("/jobs", response_model=CreateJobResponse, tags=["Jobs"], dependencies=[Depends(require_auth)])
async def create_job(
    files: list[UploadFile] = File(...),
    metadata: str = Form("{}"),
    config: str = Form("{}"),
):
    """Create a conversion job by uploading manuscript files.

    Files are saved to the job's input directory, then a worker subprocess
    is spawned to process them.
    """
    manager = _get_manager()

    # Enforce per-user job limit (exclude pre-loaded samples)
    existing = [j for j in manager.list_jobs() if not j.job_id.startswith("sample_")]
    if len(existing) >= _MAX_JOBS_PER_USER:
        raise HTTPException(429, f"Job limit reached ({_MAX_JOBS_PER_USER} max). Contact the administrator.")

    # Parse metadata and config from JSON form fields
    try:
        meta_dict = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON in metadata field")
    try:
        config_dict = json.loads(config)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON in config field")

    # Build typed models
    book_metadata = BookMetadata(
        title=meta_dict.get("title", ""),
        authors=[meta_dict["author"]] if meta_dict.get("author") else [],
        publisher_name=meta_dict.get("publisher_name", ""),
    )
    job_config = JobConfig(
        template=config_dict.get("template", "academic"),
        rewrite_percent=config_dict.get("rewrite_percent", 0),
        output_formats=config_dict.get("output_formats", ["epub"]),
        generate_title=config_dict.get("generate_title", True),
        generate_preface=config_dict.get("generate_preface", False),
        generate_acknowledgement=config_dict.get("generate_acknowledgement", False),
    )

    # Create job (gets an ID and directories)
    job = manager.create_job([], book_metadata, job_config)

    # Save uploaded files to the job's input directory
    job_dir = manager.get_job_dir(job.job_id)
    input_dir = job_dir / "input"
    saved_paths: list[Path] = []

    for upload in files:
        if not upload.filename:
            continue
        dest = input_dir / upload.filename
        content = await upload.read()
        dest.write_bytes(content)
        saved_paths.append(dest)

    # Update job with actual input files
    job.input_files = [str(p) for p in saved_paths]
    job.progress.total_files = len(saved_paths)
    manager._store.write_job(job)

    # Spawn worker
    manager.spawn_worker(job.job_id)

    return CreateJobResponse(
        job_id=job.job_id,
        status=job.status.value,
        message=f"Job created with {len(saved_paths)} file(s)",
    )


@router.get("/jobs", response_model=JobListResponse, tags=["Jobs"])
async def list_jobs():
    """List all jobs, most recent first."""
    manager = _get_manager()
    jobs = manager.list_jobs()

    items = []
    for job in jobs:
        progress = manager.get_progress(job.job_id)
        # Use live status from status.json if job.json hasn't been updated yet
        status = job.status.value
        if progress and progress.current_stage == "failed" and status in ("queued", "processing"):
            status = "failed"
        elif progress and progress.current_stage == "completed" and status in ("queued", "processing"):
            status = "completed"

        items.append(JobListItem(
            job_id=job.job_id,
            status=status,
            title=_get_job_title(job),
            created_at=job.created_at,
            total_files=job.progress.total_files,
            succeeded=progress.succeeded if progress else 0,
            failed=progress.failed if progress else 0,
        ))

    return JobListResponse(jobs=items, total=len(items))


@router.get("/jobs/{job_id}", response_model=JobResponse, tags=["Jobs"])
async def get_job(job_id: str):
    """Get full job information including progress and results."""
    manager = _get_manager()
    job = manager.get_job(job_id)

    if job is None:
        raise HTTPException(404, f"Job not found: {job_id}")

    progress = manager.get_progress(job_id)
    results = manager.get_results(job_id)

    progress_resp = None
    if progress:
        progress_resp = ProgressResponse(**asdict(progress))

    file_results = [
        FileResultResponse(
            file_path=Path(r.file_path).name,
            status=r.status,
            error=r.error,
            output_paths=[Path(p).name for p in r.output_paths],
        )
        for r in results
    ]

    return JobResponse(
        job_id=job.job_id,
        status=job.status.value,
        input_files=job.input_files,
        metadata=job.metadata if isinstance(job.metadata, dict) else {},
        config=job.config if isinstance(job.config, dict) else {},
        progress=progress_resp,
        file_results=file_results,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.get("/jobs/{job_id}/download/{filename}", tags=["Jobs"])
async def download_output(job_id: str, filename: str):
    """Download an output file from a completed job."""
    manager = _get_manager()
    job = manager.get_job(job_id)

    if job is None:
        raise HTTPException(404, f"Job not found: {job_id}")

    output_dir = manager.get_job_dir(job_id) / "output"
    file_path = output_dir / filename

    if not file_path.exists():
        raise HTTPException(404, f"File not found: {filename}")

    # Security: ensure the resolved path is within the output directory
    try:
        file_path.resolve().relative_to(output_dir.resolve())
    except ValueError:
        raise HTTPException(403, "Access denied")

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=_media_type(filename),
    )


# ---------------------------------------------------------------------------
# Cancel endpoint
# ---------------------------------------------------------------------------


@router.delete("/jobs/{job_id}", tags=["Jobs"], dependencies=[Depends(require_auth)])
async def cancel_job(job_id: str):
    """Cancel a running job."""
    manager = _get_manager()
    success = manager.cancel_job(job_id)
    if not success:
        raise HTTPException(404, f"Job not found or already completed: {job_id}")
    return {"job_id": job_id, "status": "cancelled"}


# ---------------------------------------------------------------------------
# Templates endpoint
# ---------------------------------------------------------------------------


@router.get("/templates", tags=["Templates"])
async def list_templates():
    """List available templates."""
    from bookforge.templates.loader import _find_templates_dir

    templates_dir = _find_templates_dir()
    templates = []

    if templates_dir.is_dir():
        for d in sorted(templates_dir.iterdir()):
            if d.is_dir() and (d / "config.yaml").exists():
                import yaml
                try:
                    cfg = yaml.safe_load((d / "config.yaml").read_text()) or {}
                    templates.append({
                        "name": d.name,
                        "display_name": cfg.get("display_name", d.name),
                        "description": cfg.get("description", ""),
                    })
                except Exception:
                    templates.append({"name": d.name, "display_name": d.name, "description": ""})

    return {"templates": templates, "total": len(templates)}


# ---------------------------------------------------------------------------
# Config endpoint
# ---------------------------------------------------------------------------


@router.get("/config", tags=["Config"], dependencies=[Depends(require_auth)])
async def get_config():
    """Get a summary of the current pipeline configuration."""
    global _config
    if _config is None:
        _config = Config.load()

    return {
        "templates": {
            "default": _config.get("templates.default", "academic"),
        },
        "ai": {
            "provider": _config.get("ai.provider", "anthropic"),
            "model": _config.get("ai.model", "claude-sonnet-4-6"),
        },
        "export": {
            "default_formats": _config.get("export.default_formats", ["epub"]),
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_job_title(job) -> str:
    """Get the best available title for a job."""
    # Check generated.json sidecar first
    gen_path = _get_manager().get_job_dir(job.job_id) / "generated.json"
    if gen_path.exists():
        try:
            import json
            data = json.loads(gen_path.read_text())
            if data.get("title"):
                return data["title"]
        except Exception:
            pass
    # Fall back to metadata title
    if isinstance(job.metadata, dict):
        return job.metadata.get("title") or ""
    return ""


def _media_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return {
        ".epub": "application/epub+zip",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf": "application/pdf",
    }.get(ext, "application/octet-stream")
