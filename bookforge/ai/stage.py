"""AI Stage — Stage 4 orchestrator.

Coordinates all AI sub-tasks for a single book:
  1. Title generation (optional)
  2. Preface generation (optional)
  3. Acknowledgement generation (optional)
  4. Content rewriting (optional, per-chapter, chunked)

If ALL AI features are disabled (rewrite_percent=0 and all generators off),
the entire stage is skipped and content passes through unchanged.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from bookforge.ai.base import BaseAIProvider
from bookforge.ai.generators import (
    generate_acknowledgement,
    generate_preface,
    generate_title,
)
from bookforge.ai.prompt_loader import load_prompt
from bookforge.ai.rewriter import (
    count_tokens,
    extract_protected_blocks,
    restore_protected_blocks,
    split_at_paragraphs,
)
from bookforge.core.exceptions import AIError
from bookforge.core.logging import get_logger
from bookforge.core.models import (
    AssembledBook,
    BookMetadata,
    JobConfig,
    ProcessedContent,
)

logger = get_logger("ai.stage")


def process(
    assembled: AssembledBook,
    metadata: BookMetadata,
    job_config: JobConfig,
    ai_provider: BaseAIProvider,
    config: dict,
) -> ProcessedContent:
    """Run Stage 4: AI processing on the assembled book.

    Returns ProcessedContent with generated/rewritten content. Passes
    chapter_headings and assets through unchanged.
    """
    # Check if any AI work is needed
    needs_title = job_config.generate_title
    needs_preface = job_config.generate_preface
    needs_ack = job_config.generate_acknowledgement
    needs_rewrite = job_config.rewrite_percent != 0

    if not any([needs_title, needs_preface, needs_ack, needs_rewrite]):
        logger.debug("AI stage skipped — all features disabled")
        return _passthrough(assembled)

    logger.debug(
        "AI stage starting",
        generate_title=needs_title,
        generate_preface=needs_preface,
        generate_ack=needs_ack,
        rewrite_percent=job_config.rewrite_percent,
    )

    # --- Generators ---
    generated_title = None
    generated_preface = None
    generated_ack = None

    if needs_title:
        try:
            generated_title = generate_title(assembled, ai_provider, config)
        except AIError as exc:
            logger.error("Title generation failed", error=str(exc))
            raise

    if needs_preface:
        try:
            # Use the AI-generated title if available, otherwise the metadata title
            if generated_title:
                metadata_for_preface = BookMetadata(
                    title=generated_title,
                    authors=metadata.authors,
                    publisher_name=metadata.publisher_name,
                )
            else:
                metadata_for_preface = metadata
            generated_preface = generate_preface(
                assembled, metadata_for_preface, ai_provider, config
            )
        except AIError as exc:
            logger.error("Preface generation failed", error=str(exc))
            raise

    if needs_ack:
        try:
            generated_ack = generate_acknowledgement(metadata, ai_provider, config)
        except AIError as exc:
            logger.error("Acknowledgement generation failed", error=str(exc))
            raise

    # --- Content Rewriting ---
    body_html = assembled.body_html
    if needs_rewrite:
        body_html = _rewrite_all_chapters(
            body_html,
            job_config.rewrite_percent,
            ai_provider,
            config,
        )

    # --- Build result ---
    ai_meta = {
        "skipped": False,
        "rewrite_percent": job_config.rewrite_percent,
        "title_generated": generated_title is not None,
        "preface_generated": generated_preface is not None,
        "ack_generated": generated_ack is not None,
    }
    if hasattr(ai_provider, "cost_summary"):
        ai_meta["cost"] = ai_provider.cost_summary

    return ProcessedContent(
        body_html=body_html,
        generated_title=generated_title,
        generated_preface=generated_preface,
        generated_acknowledgement=generated_ack,
        ai_metadata=ai_meta,
        chapter_headings=assembled.chapter_headings,
        assets=assembled.assets,
    )


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _passthrough(assembled: AssembledBook) -> ProcessedContent:
    """Pass content through with no AI modifications."""
    return ProcessedContent(
        body_html=assembled.body_html,
        generated_title=None,
        generated_preface=None,
        generated_acknowledgement=None,
        ai_metadata={"skipped": True},
        chapter_headings=assembled.chapter_headings,
        assets=assembled.assets,
    )


def _rewrite_all_chapters(
    body_html: str,
    rewrite_percent: int,
    ai_provider: BaseAIProvider,
    config: dict,
) -> str:
    """Split body into chapters, rewrite each, reassemble.

    Chapters are delimited by <section class="bf-chapter"> tags from the
    assembler. Each chapter is rewritten independently.
    """
    soup = BeautifulSoup(body_html, "html.parser")
    chapters = soup.find_all("section", class_="bf-chapter")

    if not chapters:
        # No chapter sections — rewrite the entire body as one chunk
        logger.debug("No bf-chapter sections found, rewriting as single block")
        return _rewrite_chapter(
            body_html, rewrite_percent, ai_provider, config
        )

    for chapter in chapters:
        # Only rewrite the inner content — preserve the <section> wrapper
        inner_html = chapter.decode_contents()
        rewritten_inner = _rewrite_chapter(
            inner_html, rewrite_percent, ai_provider, config
        )
        # Clear and replace inner content, keeping the <section> tag + attributes
        chapter.clear()
        chapter.append(BeautifulSoup(rewritten_inner, "html.parser"))

    return str(soup)


def _rewrite_chapter(
    chapter_html: str,
    rewrite_percent: int,
    ai_provider: BaseAIProvider,
    config: dict,
) -> str:
    """Rewrite a single chapter with protected block preservation and chunking.

    Strategy: split text into segments around protected block placeholders,
    rewrite only the text segments (never sending placeholders to the AI),
    and reassemble with original protected blocks. This guarantees tables
    and equations survive regardless of the AI's instruction-following.
    """
    ai_config = config.get("ai", {})
    max_chunk = ai_config.get("max_chunk_tokens", 3000)

    direction = "longer" if rewrite_percent > 0 else "shorter"
    percent = abs(rewrite_percent)

    # 1. Extract protected blocks — replaces bf-protected elements with placeholders
    text, placeholders = extract_protected_blocks(chapter_html)

    # 2. Build instruction
    instruction = load_prompt(
        "rewrite", config, direction=direction, percent=percent
    )

    # 3. Split text into segments around placeholders, rewrite only text segments
    if placeholders:
        rewritten = _rewrite_around_placeholders(
            text, placeholders, instruction, ai_provider, ai_config,
        )
    else:
        # No protected blocks — rewrite the whole thing
        rewritten = _rewrite_text(text, instruction, ai_provider, ai_config, max_chunk)

    # 4. Clean up AI artifacts
    rewritten = _clean_ai_output(rewritten)

    # 5. Restore protected blocks (for the non-placeholder path, or any that survived)
    return restore_protected_blocks(rewritten, placeholders)


def _rewrite_around_placeholders(
    text: str,
    placeholders: dict[str, str],
    instruction: str,
    ai_provider: BaseAIProvider,
    ai_config: dict,
) -> str:
    """Split text at placeholder boundaries, rewrite only text segments.

    The AI never sees placeholders — it can't drop what it doesn't receive.
    """
    import re

    # Build a regex that matches any placeholder
    placeholder_keys = sorted(placeholders.keys(), key=len, reverse=True)
    pattern = "|".join(re.escape(k) for k in placeholder_keys)
    parts = re.split(f"({pattern})", text)

    result_parts: list[str] = []
    for part in parts:
        if part in placeholders:
            # This is a placeholder — keep the original protected content
            result_parts.append(placeholders[part])
        elif part.strip():
            # This is text — rewrite it
            max_chunk = ai_config.get("max_chunk_tokens", 3000)
            rewritten_part = _rewrite_text(
                part, instruction, ai_provider, ai_config, max_chunk,
            )
            result_parts.append(_clean_ai_output(rewritten_part))
        else:
            # Whitespace — keep as-is
            result_parts.append(part)

    return "".join(result_parts)


def _rewrite_text(
    text: str,
    instruction: str,
    ai_provider: BaseAIProvider,
    ai_config: dict,
    max_chunk: int,
) -> str:
    """Rewrite a text segment (no placeholders), with chunking if needed."""
    token_count = count_tokens(text)

    if token_count <= max_chunk:
        logger.debug("Rewriting segment as single call", tokens=token_count)
        return ai_provider.rewrite(
            text, instruction, ai_config.get("max_tokens", 4096),
        )

    logger.debug("Chunking segment for rewrite", tokens=token_count, max_chunk=max_chunk)
    chunks = split_at_paragraphs(text, max_chunk)
    rewritten_chunks: list[str] = []
    prev_context = ""

    for i, chunk in enumerate(chunks):
        logger.debug("Rewriting chunk", chunk=i + 1, total=len(chunks))
        rewritten_chunk = ai_provider.rewrite(
            chunk,
            instruction,
            ai_config.get("max_tokens", 4096),
            system_context=prev_context,
        )
        rewritten_chunks.append(rewritten_chunk)
        overlap = ai_config.get("context_overlap_tokens", 200)
        prev_context = chunk[-(overlap * 4):]

    return "\n".join(rewritten_chunks)


def _clean_ai_output(text: str) -> str:
    """Strip AI prompt artifacts from output."""
    first_tag = text.find("<")
    if first_tag > 0:
        preamble = text[:first_tag]
        if any(m in preamble for m in ("---", "BEGIN REWRITE", "Here is", "Note:")):
            text = text[first_tag:]
    return text
