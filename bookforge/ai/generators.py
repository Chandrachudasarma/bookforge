"""AI content generators — title, preface, acknowledgement.

Each generator is a standalone function that:
  1. Loads the prompt template from config/prompts/
  2. Fills in variables from the assembled book metadata
  3. Calls the AI provider once
  4. Returns the generated text

Each is independently toggleable via JobConfig flags.
"""

from __future__ import annotations

from bookforge.ai.base import BaseAIProvider
from bookforge.ai.prompt_loader import load_prompt
from bookforge.core.logging import get_logger
from bookforge.core.models import AssembledBook, BookMetadata

logger = get_logger("ai.generators")


def generate_title(
    assembled: AssembledBook,
    ai_provider: BaseAIProvider,
    config: dict,
) -> str:
    """Generate a book title from the article titles.

    Uses config/prompts/title.txt with {article_titles} placeholder.
    """
    article_titles = ", ".join(assembled.article_titles) or "Untitled articles"

    prompt = load_prompt("title", config, article_titles=article_titles)

    logger.debug("Generating title", article_count=len(assembled.article_titles))
    title = ai_provider.generate(prompt, context="", max_tokens=100)

    # Clean up: strip quotes, whitespace, trailing periods
    title = title.strip().strip('"\'').strip()
    if title.endswith("."):
        title = title[:-1]

    logger.debug("Title generated", title=title)
    return title


def generate_preface(
    assembled: AssembledBook,
    metadata: BookMetadata,
    ai_provider: BaseAIProvider,
    config: dict,
) -> str:
    """Generate a preface for the book.

    Uses config/prompts/preface.txt with {book_title} and {article_titles}.
    """
    book_title = metadata.title or "Untitled"
    article_titles = ", ".join(assembled.article_titles) or "various articles"

    prompt = load_prompt(
        "preface",
        config,
        book_title=book_title,
        article_titles=article_titles,
    )

    logger.debug("Generating preface")
    preface = ai_provider.generate(prompt, context="", max_tokens=2000)

    return preface.strip()


def generate_acknowledgement(
    metadata: BookMetadata,
    ai_provider: BaseAIProvider,
    config: dict,
) -> str:
    """Generate an acknowledgements section.

    Uses config/prompts/acknowledgement.txt with {book_title} and {publisher_name}.
    """
    prompt = load_prompt(
        "acknowledgement",
        config,
        book_title=metadata.title or "Untitled",
        publisher_name=metadata.publisher_name or "the publisher",
    )

    logger.debug("Generating acknowledgement")
    ack = ai_provider.generate(prompt, context="", max_tokens=500)

    return ack.strip()
