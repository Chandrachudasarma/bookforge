"""Calibre post-processing for EPUB files.

Calibre's ebook-polish improves cover embedding, metadata normalisation,
and cross-reader compatibility. It is optional — the pipeline works
without it, but output quality is better with it.

If Calibre is not installed, all functions return the original path unchanged.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from bookforge.core.logging import get_logger

logger = get_logger("export.calibre")


def find_calibre_binary(name: str) -> str | None:
    """Find a Calibre CLI binary by name.

    Checks PATH first, then the macOS application bundle location.
    """
    if shutil.which(name):
        return name
    macos_path = f"/Applications/calibre.app/Contents/MacOS/{name}"
    if Path(macos_path).exists():
        return macos_path
    return None


def polish_epub(epub_path: Path, timeout: int = 120) -> Path:
    """Run Calibre ebook-polish on an EPUB file.

    Returns the polished EPUB path, or the original if Calibre is unavailable
    or polishing fails.
    """
    binary = find_calibre_binary("ebook-polish")
    if not binary:
        logger.debug("Calibre ebook-polish not installed — skipping EPUB polish")
        return epub_path

    polished_path = epub_path.with_stem(epub_path.stem + "_polished")

    try:
        result = subprocess.run(
            [binary, str(epub_path), str(polished_path)],
            capture_output=True,
            timeout=timeout,
        )
        if result.returncode == 0 and polished_path.exists():
            logger.debug("Calibre polish complete", path=str(polished_path))
            return polished_path
        else:
            logger.warning(
                "Calibre polish failed — using unpolished EPUB",
                returncode=result.returncode,
            )
    except subprocess.TimeoutExpired:
        logger.warning("Calibre polish timed out — using unpolished EPUB")
    except OSError as exc:
        logger.warning("Calibre polish error", error=str(exc))

    return epub_path
