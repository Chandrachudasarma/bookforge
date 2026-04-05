"""Equation Detector — fourth sub-step of Stage 2 (Normalize).

Detects LaTeX and MathML equations and tags them as bf-protected blocks
so the AI rewriter skips them entirely.

Detection order (most-to-least reliable):
1. MathML  — structural, minimal false positives
2. LaTeX display  — $$...$$ and \\begin{equation}
3. LaTeX inline   — $...$ (with heuristic to skip dollar amounts)
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from bookforge.core.models import ProtectedBlock, ProtectedBlockType

# LaTeX display: $$...$$ or \begin{equation}...\end{equation}
_LATEX_DISPLAY = re.compile(
    r"(\$\$[\s\S]+?\$\$|\\begin\{(?:equation|align|gather|multline)\*?\}[\s\S]+?\\end\{(?:equation|align|gather|multline)\*?\})",
    re.DOTALL,
)

# LaTeX inline: $...$
# Heuristics to avoid matching dollar amounts:
#   - Not preceded or followed by a digit immediately
#   - No leading/trailing space inside the delimiters
#   - At least 1 non-space character inside
_LATEX_INLINE = re.compile(
    r"(?<!\d)\$(?!\s)([^\$\n]+?)(?<!\s)\$(?!\d)",
)


def detect_equations(
    html: str, block_counter: int = 0
) -> tuple[str, list[ProtectedBlock], int]:
    """Find and tag all equations as bf-protected.

    MathML tags are modified in-place in the DOM.
    LaTeX strings in text nodes are wrapped in <span class="bf-protected">.

    Returns:
        (modified_html, new_protected_blocks, updated_counter)
    """
    soup = BeautifulSoup(html, "lxml")
    blocks: list[ProtectedBlock] = []

    # --- MathML ---
    for math_tag in soup.find_all("math"):
        if not isinstance(math_tag, Tag):
            continue
        block_id = f"PROTECTED_{block_counter}"
        block_counter += 1
        original = str(math_tag)

        existing = math_tag.get("class", [])
        if isinstance(existing, str):
            existing = [existing]
        math_tag["class"] = list(existing) + ["bf-protected"]
        math_tag["data-type"] = "equation"
        math_tag["data-block-id"] = block_id

        blocks.append(
            ProtectedBlock(
                block_id=block_id,
                block_type=ProtectedBlockType.EQUATION,
                original_html=original,
                source_format="mathml",
            )
        )

    # --- LaTeX in text nodes ---
    # We need to handle the HTML as a string for regex-based LaTeX detection
    # because LaTeX may span across text nodes or be inside <p> tags.
    modified_html = str(soup)

    # Display first (so $$ isn't double-matched by inline)
    modified_html, blocks, block_counter = _wrap_latex(
        modified_html, blocks, block_counter,
        pattern=_LATEX_DISPLAY,
        source_format="latex_display",
    )
    modified_html, blocks, block_counter = _wrap_latex(
        modified_html, blocks, block_counter,
        pattern=_LATEX_INLINE,
        source_format="latex_inline",
    )

    return modified_html, blocks, block_counter


def _wrap_latex(
    html: str,
    blocks: list[ProtectedBlock],
    counter: int,
    pattern: re.Pattern,
    source_format: str,
) -> tuple[str, list[ProtectedBlock], int]:
    """Replace each pattern match with a bf-protected <span>."""

    def replacer(m: re.Match) -> str:
        nonlocal counter
        block_id = f"PROTECTED_{counter}"
        counter += 1
        original = m.group(0)
        blocks.append(
            ProtectedBlock(
                block_id=block_id,
                block_type=ProtectedBlockType.EQUATION,
                original_html=original,
                source_format=source_format,
            )
        )
        return (
            f'<span class="bf-protected" data-type="equation" '
            f'data-block-id="{block_id}">{original}</span>'
        )

    return pattern.sub(replacer, html), blocks, counter
