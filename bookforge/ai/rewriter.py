"""Content Rewriter — Stage 4 AI sub-module.

Handles the extract→rewrite→restore cycle that protects equations,
tables, and figure captions from being modified by the AI.

This module also contains the chunked rewriting logic for chapters
that exceed the AI model's context window.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from bookforge.core.logging import get_logger

logger = get_logger("ai.rewriter")

# Placeholder pattern used in AI prompts
_PLACEHOLDER_PATTERN = re.compile(r"<<<PROTECTED_\d+>>>")


# ---------------------------------------------------------------------------
# Protected block extract / restore
# ---------------------------------------------------------------------------


def extract_protected_blocks(html: str) -> tuple[str, dict[str, str]]:
    """Replace bf-protected elements with <<<PROTECTED_N>>> placeholders.

    The placeholders are safe to send to an AI model — they contain no
    equations or table markup that the AI might accidentally rewrite.

    Returns:
        (cleaned_html, {placeholder_key: original_html_string})
    """
    soup = BeautifulSoup(html, "html.parser")
    placeholders: dict[str, str] = {}

    # Find all bf-protected elements (equations, tables, figure captions)
    for el in soup.find_all(class_="bf-protected"):
        block_id = el.get("data-block-id")
        if not block_id:
            continue
        key = f"<<<{block_id}>>>"
        placeholders[key] = str(el)
        el.replace_with(key)

    # formatter=None prevents BS from escaping <<< >>> in placeholders
    return soup.decode(formatter=None), placeholders


def restore_protected_blocks(rewritten: str, placeholders: dict[str, str]) -> str:
    """Restore original protected content from placeholder strings.

    Handles cases where the AI slightly modified the placeholder text
    by doing a fuzzy search if an exact match fails.
    """
    for key, original in placeholders.items():
        if key in rewritten:
            rewritten = rewritten.replace(key, original)
        else:
            # AI may have stripped or modified the placeholder — try to fix
            # by searching for the block_id portion
            block_id = key.strip("<>")
            fuzzy_pattern = re.compile(
                r"<<<\s*" + re.escape(block_id) + r"\s*>>>",
                re.IGNORECASE,
            )
            rewritten = fuzzy_pattern.sub(original, rewritten)

    return rewritten


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------


def count_tokens(text: str, model: str = "claude-sonnet-4-6") -> int:
    """Estimate token count for the given text.

    Uses tiktoken's cl100k_base encoding as a proxy for Claude models.
    Actual Claude token counts may differ slightly.
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        # Rough fallback: ~4 characters per token
        return len(text) // 4


# ---------------------------------------------------------------------------
# Paragraph-level chunking
# ---------------------------------------------------------------------------


def split_at_paragraphs(text: str, max_tokens: int) -> list[str]:
    """Split HTML text into chunks at <p> tag boundaries.

    Each chunk will be at most max_tokens tokens. Never splits mid-paragraph.
    """
    # Parse paragraphs from HTML
    soup = BeautifulSoup(text, "lxml")
    paragraphs = soup.find_all("p")

    if not paragraphs:
        # No paragraph tags — split by double newline
        return _split_plain_text(text, max_tokens)

    chunks: list[str] = []
    current_parts: list[str] = []
    current_tokens = 0

    for p in paragraphs:
        p_html = str(p)
        p_tokens = count_tokens(p_html)

        if current_tokens + p_tokens > max_tokens and current_parts:
            chunks.append("\n".join(current_parts))
            current_parts = []
            current_tokens = 0

        current_parts.append(p_html)
        current_tokens += p_tokens

    if current_parts:
        chunks.append("\n".join(current_parts))

    return chunks if chunks else [text]


def _split_plain_text(text: str, max_tokens: int) -> list[str]:
    """Split plain text into token-bounded chunks at newline boundaries."""
    lines = text.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for line in lines:
        line_tokens = count_tokens(line)
        if current_tokens + line_tokens > max_tokens and current:
            chunks.append("\n".join(current))
            current = []
            current_tokens = 0
        current.append(line)
        current_tokens += line_tokens

    if current:
        chunks.append("\n".join(current))

    return chunks if chunks else [text]
