"""Four-layer config loader.

Merge order: default.yaml → local.yaml → env vars → job-level overrides.
Later layers override earlier ones. The merged result is a flat-access
Config object supporting dot-path lookups (config.get("ai.model")).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from bookforge.core.exceptions import ConfigError


class Config:
    """Immutable merged configuration.

    Built once at startup via Config.load(). Job-level overrides produce
    a new Config without modifying the base.
    """

    def __init__(self, data: dict):
        self._data = data

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, job_overrides: dict | None = None) -> "Config":
        """Load and merge all config layers."""
        base = _load_yaml(_find_config("config/default.yaml"))
        local = _load_yaml(_find_config("config/local.yaml"), required=False)
        env = _extract_env_vars(prefix="BOOKFORGE_")
        merged = _deep_merge(base, local, env, job_overrides or {})
        return cls(merged)

    def with_overrides(self, overrides: dict) -> "Config":
        """Return a new Config with additional overrides applied."""
        return Config(_deep_merge(self._data, overrides))

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def get(self, dot_path: str, default: Any = None) -> Any:
        """Retrieve a value by dot-separated path.

        Example: config.get("ai.model") → "claude-sonnet-4-6"
        """
        keys = dot_path.split(".")
        node = self._data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def require(self, dot_path: str) -> Any:
        """Like get() but raises ConfigError if the key is missing."""
        value = self.get(dot_path)
        if value is None:
            raise ConfigError(f"Required config key missing: {dot_path}")
        return value

    def as_dict(self) -> dict:
        return dict(self._data)

    def __repr__(self) -> str:  # pragma: no cover
        return f"Config({list(self._data.keys())})"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_config(relative_path: str) -> Path:
    """Resolve a config path relative to the project root."""
    # Walk up from CWD to find a directory containing pyproject.toml
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "pyproject.toml").exists():
            return parent / relative_path
    return cwd / relative_path


def _load_yaml(path: Path, required: bool = True) -> dict:
    if not path.exists():
        if required:
            raise ConfigError(f"Config file not found: {path}")
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc


def _extract_env_vars(prefix: str) -> dict:
    """Convert BOOKFORGE_AI_MODEL → {"ai": {"model": value}}.

    Limitation: only handles 2-level paths (SECTION_KEY).
    3-level paths like export.epub.equation_mode cannot be set via env vars
    (BOOKFORGE_EXPORT_EPUB_EQUATION_MODE would become {"export": {"epub_equation_mode": ...}}).
    Use config/local.yaml for 3-level overrides.
    """
    result: dict = {}
    prefix_len = len(prefix)
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        parts = key[prefix_len:].lower().split("_", 1)
        if len(parts) == 2:
            section, name = parts
            result.setdefault(section, {})[name] = _coerce(value)
        else:
            result[parts[0]] = _coerce(value)
    return result


def _coerce(value: str) -> Any:
    """Coerce env var string to bool/int/float when unambiguous.

    Booleans only match explicit words — never "0" or "1" — so that
    BOOKFORGE_PIPELINE_MAX_CONCURRENT_FILES=0 stays an integer, not False.
    """
    if value.lower() in ("true", "yes"):
        return True
    if value.lower() in ("false", "no"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _deep_merge(*dicts: dict) -> dict:
    """Deep-merge multiple dicts left to right. Later dicts win."""
    result: dict = {}
    for d in dicts:
        if not d:
            continue
        for key, value in d.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = _deep_merge(result[key], value)
            else:
                result[key] = value
    return result
