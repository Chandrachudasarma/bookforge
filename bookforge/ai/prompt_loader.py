"""Prompt loader — reads prompt templates from config/prompts/.

Prompts are plain text files with {variable} placeholders. No prompt
strings are hardcoded in source code — all live in config/prompts/.
"""

from __future__ import annotations

from pathlib import Path

from bookforge.core.exceptions import ConfigError
from bookforge.core.logging import get_logger

logger = get_logger("ai.prompt_loader")


def load_prompt(name: str, config: dict, **variables) -> str:
    """Load a prompt template and substitute variables.

    Args:
        name:      Prompt file name without extension (e.g. "title", "rewrite").
        config:    App config dict containing ai.prompts_dir.
        **variables: Key-value pairs to substitute into {placeholders}.

    Returns:
        The fully rendered prompt string.

    Raises:
        ConfigError: If the prompt file does not exist.
    """
    prompts_dir = Path(config.get("ai", {}).get("prompts_dir", "config/prompts"))
    prompt_path = prompts_dir / f"{name}.txt"

    if not prompt_path.exists():
        raise ConfigError(f"Prompt file not found: {prompt_path}")

    template = prompt_path.read_text(encoding="utf-8")

    if variables:
        try:
            return template.format(**variables)
        except KeyError as exc:
            raise ConfigError(
                f"Prompt '{name}' requires variable {exc} but it was not provided"
            ) from exc

    return template
