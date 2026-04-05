"""Equation renderer — converts equations to PNG images for embedding.

MVP: all equations render to PNG via matplotlib.mathtext.
Phase 2: OMML (editable equations in DOCX) via LaTeX → MathML → OMML.

Known limitations of matplotlib.mathtext:
  - Multi-line aligned equations (\\begin{align}) are not supported
  - \\text{} with non-ASCII characters may fail
  - Falls back to monospace text rendering on parse failure (logged as warning)
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from bookforge.core.logging import get_logger
from bookforge.core.models import Asset

logger = get_logger("export.equation_renderer")

# Matches <span class="bf-protected" data-type="equation" ...>...</span>
# and <math ...>...</math> (MathML)
_EQUATION_SPAN = re.compile(
    r'<span[^>]*class="[^"]*bf-protected[^"]*"[^>]*data-type="equation"[^>]*>(.*?)</span>',
    re.DOTALL,
)
_MATHML_TAG = re.compile(r"<math[\s>].*?</math>", re.DOTALL)


def render_equations_to_images(
    html: str,
    temp_dir: Path,
    dpi: int = 300,
) -> tuple[str, list[Asset]]:
    """Replace equation spans in HTML with <img> tags pointing to PNG files.

    Returns:
        (modified_html, list_of_new_image_assets)
    """
    assets: list[Asset] = []

    def replace_equation(match: re.Match) -> str:
        inner = match.group(1).strip()
        latex = _extract_latex(inner)

        img_path = _render_to_png(latex, temp_dir, dpi)
        if img_path is None:
            # Fallback: keep original HTML
            return match.group(0)

        filename = img_path.name
        assets.append(
            Asset(
                filename=filename,
                media_type="image/png",
                file_path=img_path,
                size_bytes=img_path.stat().st_size,
            )
        )
        alt_text = _escape(latex[:80])
        return f'<img src="images/{filename}" alt="{alt_text}" class="equation"/>'

    modified = _EQUATION_SPAN.sub(replace_equation, html)
    return modified, assets


def _extract_latex(inner_html: str) -> str:
    """Extract LaTeX string from equation span inner content."""
    # Strip any remaining HTML tags
    clean = re.sub(r"<[^>]+>", "", inner_html).strip()

    # Remove LaTeX delimiters for matplotlib: $...$, $$...$$
    if clean.startswith("$$") and clean.endswith("$$"):
        clean = clean[2:-2].strip()
    elif clean.startswith("$") and clean.endswith("$"):
        clean = clean[1:-1].strip()
    elif clean.startswith(r"\begin"):
        # Display equation — use as-is (matplotlib handles \begin{equation})
        pass

    return clean


def _render_to_png(latex: str, temp_dir: Path, dpi: int) -> Path | None:
    """Render a LaTeX expression to a PNG file using matplotlib.

    Returns the path to the PNG, or None if rendering failed.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not installed — equation rendering unavailable")
        return None

    temp_dir.mkdir(parents=True, exist_ok=True)

    # Stable filename from content hash
    h = hashlib.md5(latex.encode()).hexdigest()[:12]
    img_path = temp_dir / f"eq_{h}.png"

    if img_path.exists():
        return img_path

    try:
        fig = plt.figure(figsize=(0.01, 0.01))
        # Use raw string to pass to mathtext
        math_str = f"${latex}$"
        text = fig.text(0, 0, math_str, fontsize=12, color="black")
        fig.savefig(
            img_path,
            dpi=dpi,
            bbox_inches="tight",
            pad_inches=0.05,
            transparent=True,
        )
        plt.close(fig)
        return img_path

    except Exception as exc:
        logger.warning(
            "Equation rendering failed — falling back to text",
            latex=latex[:60],
            error=str(exc),
        )
        plt.close("all")
        return None


def _escape(text: str) -> str:
    return text.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
