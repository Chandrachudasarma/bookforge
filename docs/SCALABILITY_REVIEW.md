# BookForge — Expert Panel: Scalability Review

**Date:** 2026-04-05
**Focus:** Scalability against client requirements
**Mode:** Critique
**Panel:** Nygard (production systems), Newman (distributed systems), Fowler (architecture), Hightower (cloud-native)

---

## Client's Scalability Requirements (Exact Words)

From the spec:

> - "Must support: Batch processing, Future API integration, Multi-user expansion"
> - "50–100 files per batch"
> - "Should not crash on large files"
> - "Process via queue system"
> - "Scalable"
> - "This project will expand significantly" (long-term)

---

## Panel Assessment

### MICHAEL NYGARD — Production Systems & Failure Modes

**Overall:** The error isolation is excellent — file-level try/except with typed exceptions, batch never crashes. That's the right pattern. But there are **four production concerns**:

#### Issue 1: BackgroundTasks is a time bomb for 100-file batches
**Severity:** CRITICAL

FastAPI's `BackgroundTasks` runs in the same process as the web server. A 100-file batch with OCR + AI rewriting could take **3–8 hours**. During that time:
- The web server's event loop is partially blocked
- A server restart kills the job with no recovery
- No progress persistence — if it dies at file 87, you start from 0
- Memory pressure from 100 sequential processing runs accumulates

**Recommendation:** Even for MVP, use a simple **subprocess-based worker** or `asyncio` task pool with file-based progress checkpointing. Not full Celery, but something that:
1. Survives web server restarts
2. Checkpoints progress per file (resume from file 88 if it crashed at 87)
3. Runs in a separate process from the API server

```python
# Instead of BackgroundTasks, use:
# 1. Write job config to disk as JSON
# 2. Spawn a worker subprocess: `python -m bookforge.worker --job-id {id}`
# 3. Worker reads job config, processes files, writes status to disk
# 4. API reads status from disk for polling
```

This is 50 lines of code, not infrastructure. And it's the difference between "demo" and "deliverable."

#### Issue 2: No progress tracking
**Severity:** HIGH

Client will submit 100 files and see... nothing... for hours. The Job model has `CREATED → QUEUED → PROCESSING → COMPLETED` but no per-file progress. They need:
- "Processing file 47/100: article_thermodynamics.pdf (Stage 3: AI Rewriting)"
- Estimated time remaining
- Ability to see which files succeeded so far

**Recommendation:** Add `progress` field to Job model:
```python
@dataclass
class JobProgress:
    total_files: int
    completed_files: int
    current_file: str
    current_stage: str
    succeeded: int
    failed: int
```

#### Issue 3: No file size guard
**Severity:** MEDIUM

"Should not crash on large files" — but the architecture loads `Asset.data: bytes` into memory. A 500MB PDF with 200 high-res images will OOM the process.

**Recommendation:** Assets should be **file-backed**, not memory-backed:
```python
@dataclass
class Asset:
    filename: str
    media_type: str
    file_path: Path          # NOT bytes — stored on disk in temp dir
    size_bytes: int
```

Add a `max_file_size_mb` check in the ingestion stage. Files exceeding the limit get logged and skipped.

#### Issue 4: Temp file cleanup
**Severity:** LOW

The pipeline generates intermediate files (OCR output, normalized HTML, exported books). No cleanup strategy is documented. After 1000 batches, `/tmp/bookforge` will eat disk.

**Recommendation:** Each job gets a temp directory. Clean up on job completion (or after 24h for debugging). Document the cleanup policy.

---

### SAM NEWMAN — Distributed Systems & Service Boundaries

**Overall:** The modular architecture is well-bounded. The 5-stage pipeline with clean interfaces between stages is the right pattern. **But the scalability story has a sequencing problem.**

#### Issue 5: The AI stage is the bottleneck — and it's not parallelizable in this design
**Severity:** HIGH

For a 100-file batch with 25% rewriting, each file makes ~3–5 AI API calls (title + preface + ack + N chapters rewriting). That's **300–500 API calls per batch**.

At ~2 seconds per call = **10–17 minutes just for AI**, sequential. With rate limits, could be much longer.

The current design processes files **sequentially** within a batch. Files are independent — there's no reason file 1 must finish before file 2 starts.

**Recommendation:** Even in MVP, add **file-level parallelism**:
```python
# In pipeline.py, process files concurrently:
import asyncio

async def process_batch(files: list[Path], config: JobConfig):
    semaphore = asyncio.Semaphore(config.max_concurrent_files)  # default: 4
    
    async def process_one(f):
        async with semaphore:
            return await pipeline.process_file(f, config)
    
    results = await asyncio.gather(
        *[process_one(f) for f in files],
        return_exceptions=True
    )
```

This is a significant throughput improvement with minimal complexity. 4 concurrent files = 4x faster batches.

#### Issue 6: AI rate limiting needs a strategy
**Severity:** MEDIUM

The architecture says "retry 3x with exponential backoff" for AI failures. But with 500 calls per batch, you need:
- Token budget tracking (don't blow through $200 of API credits on one batch)
- Rate limit awareness (stay under provider limits proactively, don't just retry)
- Cost estimation before starting ("This batch will use ~$15 of API credits. Proceed?")

**Recommendation:** Add `ai/rate_limiter.py` with a token bucket or sliding window. Track cost per job.

#### Issue 7: The upgrade path from MVP to multi-user is unclear
**Severity:** LOW (for MVP)

The spec says "future multi-user expansion." The current in-memory job store has no concept of users, permissions, or job isolation. The upgrade isn't just "swap in Celery" — it's:
1. Add user model
2. Add auth
3. Add job-user association
4. Add per-user file storage
5. Replace in-memory store with database
6. Add Celery workers

That's not a Phase 2 bolt-on — it's a partial rewrite of the jobs layer.

**Recommendation:** No action needed for MVP, but document that the Phase 2 multi-user upgrade will require:
- Database (SQLite → PostgreSQL)
- Job model refactor (add `user_id`)
- File storage abstraction (local → S3-compatible)

---

### MARTIN FOWLER — Software Architecture & Design Patterns

**Overall:** The architecture is clean. The 5-stage pipeline with plugin interfaces is a textbook Pipes and Filters pattern, well-applied. Two observations:

#### Issue 8: The pipeline is synchronous and rigid — consider making stages composable
**Severity:** LOW

The current pipeline always runs all 5 stages in order. But some use cases skip stages:
- EPUB → DOCX: skip normalization? (EPUB is already structured)
- No AI requested: skip Stage 3 entirely
- Preview mode: run through Stage 4, skip Stage 5

The architecture handles "skip AI" but the pipeline is still a fixed sequence.

**Recommendation:** This is fine for MVP. But note that a **pipeline builder** pattern would make it more flexible:
```python
pipeline = (
    PipelineBuilder()
    .add(IngestStage())
    .add(NormalizeStage())
    .add_if(config.ai_enabled, AIStage())
    .add(StructureStage())
    .add(ExportStage())
    .build()
)
```

Not needed now, but keeps the door open for Phase 2 "advanced workflows."

#### Issue 9: Data models use dataclasses — consider Pydantic
**Severity:** LOW

The architecture uses `@dataclass` for all models. FastAPI already depends on Pydantic. Using Pydantic `BaseModel` instead gives:
- Automatic validation
- JSON serialization (needed for API responses and job persistence)
- Schema generation (auto-docs)

**Recommendation:** Use Pydantic for models that cross API boundaries (Job, BookMetadata, BatchReport). Keep dataclasses for internal pipeline models if you prefer, but be consistent.

---

### KELSEY HIGHTOWER — Cloud Native & Operations

**Overall:** The Docker story is good — Dockerfile + docker-compose. But there are **operational gaps** that a build server deployment will hit:

#### Issue 10: No resource limits per job
**Severity:** MEDIUM

Client says "scales easily on a build server." On a build server, BookForge will share resources with other processes. A 100-file OCR batch will eat all CPU cores unless bounded.

**Recommendation:** Add configurable resource limits:
```yaml
# config/default.yaml
pipeline:
  max_concurrent_files: 4          # Parallel file processing
  max_memory_per_file_mb: 512      # Kill file processing if exceeds
  per_file_timeout_seconds: 300
  
ocr:
  max_concurrent_pages: 2          # OCR is CPU-heavy, limit parallelism
```

In Docker, also set container limits: `--memory 4g --cpus 2`.

#### Issue 11: No health check beyond `/health`
**Severity:** LOW

The `/health` endpoint exists but what does it check? For a build server, you need:
- Is the worker process alive?
- Is Tesseract installed and working?
- Is the AI API reachable?
- Is disk space sufficient?

**Recommendation:** Make `/health` a real health check:
```json
{
  "status": "healthy",
  "checks": {
    "worker": "running",
    "tesseract": "installed (v5.3.1)",
    "pandoc": "installed (v3.1)",
    "calibre": "installed (v7.2)",
    "ai_provider": "reachable (anthropic)",
    "disk_space_gb": 24.5,
    "active_jobs": 1
  }
}
```

#### Issue 12: Logging needs structure
**Severity:** LOW

Architecture mentions "structured logging" but doesn't specify format. For a build server, you need machine-parseable logs.

**Recommendation:** Use JSON structured logging:
```json
{"timestamp": "2026-04-05T14:30:00Z", "level": "INFO", "job_id": "abc-123", "file": "article.pdf", "stage": "ocr", "message": "OCR completed", "duration_ms": 4521}
```

---

## Consolidated Findings

### Severity Summary

| Severity | Count | Issues |
|---|---|---|
| CRITICAL | 1 | #1: BackgroundTasks won't survive 100-file batches |
| HIGH | 2 | #2: No progress tracking; #5: No file-level parallelism |
| MEDIUM | 3 | #3: Assets in memory; #6: AI rate limiting; #10: No resource limits |
| LOW | 6 | #4, #7, #8, #9, #11, #12 |

### Does It Meet Client's Scalability Requirements?

| Requirement | Verdict | Details |
|---|---|---|
| "50–100 files per batch" | **PARTIAL** | Will work, but takes 3–8 hours sequential. Unacceptable UX without progress tracking and parallelism. |
| "Should not crash on large files" | **PARTIAL** | No file size guard, assets stored as bytes in memory. A 500MB PDF will OOM. |
| "Process via queue system" | **FAIL** | BackgroundTasks is not a queue system. It's a fire-and-forget with no persistence, no resume, no visibility. |
| "Scalable" | **PARTIAL** | Plugin architecture scales well for adding formats/features. But compute scaling (parallelism, resource management) is weak. |
| "Future API integration" | **PASS** | REST API is well-designed, versioned, standard. |
| "Multi-user expansion" | **PARTIAL** | Architecture supports it in theory but the upgrade path is undocumented and non-trivial. |

### Expert Consensus

> The **architectural patterns are correct** — 5-stage pipeline, plugin interfaces, clean separation. These are solid foundations that will scale well as requirements grow.
>
> The **compute execution model is too naive** for MVP. `BackgroundTasks` with sequential processing and in-memory state is a demo, not a deliverable. The client specified a "queue system" and "50–100 files" — they expect to submit a batch and come back later to results, with visibility into progress.
>
> **Three changes make this production-worthy for MVP**, without adding infrastructure:
> 1. Subprocess-based worker with file-based state (survives restarts)
> 2. File-level parallelism via asyncio semaphore (4x throughput)
> 3. Per-file progress tracking (client can see what's happening)

---

## Recommended Architecture Changes

### Change A: Replace BackgroundTasks with subprocess worker (CRITICAL)

```
CURRENT:
  API → BackgroundTasks → pipeline.process() in-process

PROPOSED:
  API → writes job.json to disk → spawns worker subprocess
  Worker → reads job.json → processes files → writes status.json per file
  API → reads status.json for polling
```

Benefits:
- Worker survives API restart
- Worker crash doesn't kill API
- Progress is persisted to disk
- Can run multiple workers later (pre-Celery scaling)

Implementation: ~100 lines of code. No new dependencies.

### Change B: Add file-level parallelism (HIGH)

```python
# In worker process:
async def run_job(job: Job):
    semaphore = asyncio.Semaphore(job.config.max_concurrent_files)
    tasks = [process_with_semaphore(f, semaphore) for f in job.input_files]
    results = await asyncio.gather(*tasks, return_exceptions=True)
```

Benefits: 4x throughput with `max_concurrent_files: 4`.
Implementation: ~30 lines of code.

### Change C: File-backed assets (MEDIUM)

```python
# BEFORE:
@dataclass
class Asset:
    data: bytes              # Entire file in memory

# AFTER:
@dataclass
class Asset:
    file_path: Path          # Reference to temp file on disk
    size_bytes: int
    media_type: str
```

Benefits: Processes 500MB PDFs without OOM.
Implementation: ~20 lines changed across ingestion/export.

### Change D: Progress tracking (HIGH)

```python
@dataclass
class JobProgress:
    total_files: int
    completed_files: int
    current_file: str | None
    current_stage: str | None
    succeeded: int
    failed: int
    elapsed_seconds: float
```

Exposed via `GET /api/v1/jobs/{id}` — client polls for progress.
Implementation: ~40 lines.

---

## Final Verdict

**Architecture quality: 8/10** — Excellent patterns, clean interfaces, good extensibility.
**Scalability for MVP: 5/10** — Needs the four changes above to actually handle 100-file batches reliably.
**Scalability for Phase 2: 7/10** — Good foundations, but multi-user upgrade path needs documenting.

With Changes A–D applied, scalability score becomes **8/10** for MVP — more than sufficient for the client's stated requirements without adding any infrastructure beyond what's already designed.
