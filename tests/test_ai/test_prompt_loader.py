"""Tests for the prompt loader."""

from pathlib import Path

import pytest

from bookforge.ai.prompt_loader import load_prompt
from bookforge.core.exceptions import ConfigError


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "prompts"
    d.mkdir()
    return d


@pytest.fixture
def config_with_prompts(prompts_dir: Path) -> dict:
    return {"ai": {"prompts_dir": str(prompts_dir)}}


def test_loads_prompt_file(prompts_dir, config_with_prompts):
    (prompts_dir / "title.txt").write_text("Generate a title for: {article_titles}")
    result = load_prompt("title", config_with_prompts, article_titles="A, B, C")
    assert result == "Generate a title for: A, B, C"


def test_raises_on_missing_file(config_with_prompts):
    with pytest.raises(ConfigError, match="Prompt file not found"):
        load_prompt("nonexistent", config_with_prompts)


def test_raises_on_missing_variable(prompts_dir, config_with_prompts):
    (prompts_dir / "title.txt").write_text("Title for: {article_titles}")
    # Providing *some* variables triggers .format() — missing ones raise
    with pytest.raises(ConfigError, match="requires variable"):
        load_prompt("title", config_with_prompts, other_var="x")


def test_loads_without_variables(prompts_dir, config_with_prompts):
    (prompts_dir / "simple.txt").write_text("No variables here.")
    result = load_prompt("simple", config_with_prompts)
    assert result == "No variables here."


def test_multiple_variables(prompts_dir, config_with_prompts):
    (prompts_dir / "rewrite.txt").write_text("Make {direction} by {percent}%")
    result = load_prompt(
        "rewrite", config_with_prompts, direction="longer", percent=20
    )
    assert result == "Make longer by 20%"
