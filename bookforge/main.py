"""BookForge FastAPI application entry point.

Start with: uvicorn bookforge.main:app --reload --port 8000
"""

from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from bookforge import __version__
from bookforge.core.config import Config
from bookforge.core.logging import configure_logging

# Disable Swagger/OpenAPI in production (set BOOKFORGE_ENV=development to enable)
_is_dev = os.environ.get("BOOKFORGE_ENV", "production") == "development"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: configure logging, init API, ensure directories."""
    config = Config.load()
    configure_logging(
        level=config.get("logging.level", "INFO"),
        json_output=config.get("logging.format", "json") == "json",
    )
    data_dir = Path(config.get("worker.state_dir", "data/jobs"))
    data_dir.mkdir(parents=True, exist_ok=True)

    # Initialize API with config
    from bookforge.api.routes import init_api
    from bookforge.api.auth import init_auth
    init_api(config)
    init_auth(config)

    yield


app = FastAPI(
    title="BookForge",
    description="Automated publishing pipeline: manuscripts to EPUB, DOCX, and PDF",
    version=__version__,
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Security: strip filesystem paths from error responses
# ---------------------------------------------------------------------------

_PATH_PATTERN = re.compile(r"(/[\w./-]+){3,}")


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Strip internal file paths from error messages."""
    msg = str(exc)
    safe_msg = _PATH_PATTERN.sub("[internal path]", msg)
    return JSONResponse(status_code=500, content={"detail": safe_msg})

# Mount static UI files
_static_dir = Path(__file__).parent / "ui" / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", include_in_schema=False)
async def root():
    """Serve the web UI."""
    index = Path(__file__).parent / "ui" / "static" / "index.html"
    if index.exists():
        return FileResponse(str(index), media_type="text/html")
    return {"message": "BookForge API", "docs": "/docs"}


@app.get("/health", tags=["Health"])
async def health():
    """Dependency health check."""
    import shutil
    return {
        "status": "ok",
        "version": __version__,
        "dependencies": {
            "tesseract": bool(shutil.which("tesseract")),
            "pandoc": bool(shutil.which("pandoc")),
            "calibre": bool(
                shutil.which("ebook-polish")
                or Path("/Applications/calibre.app/Contents/MacOS/ebook-polish").exists()
            ),
        },
    }


from bookforge.api.routes import router as api_router
app.include_router(api_router, prefix="/api/v1")
