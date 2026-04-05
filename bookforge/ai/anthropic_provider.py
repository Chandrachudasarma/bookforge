"""Anthropic AI provider — Claude API implementation.

Implements BaseAIProvider using the Anthropic SDK. Includes:
  - Rate limiting (configurable RPM)
  - Cost tracking with per-job budget cap
  - Retry with exponential backoff (3 attempts)
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field

import anthropic

from bookforge.ai.base import BaseAIProvider
from bookforge.core.exceptions import AIError
from bookforge.core.logging import get_logger
from bookforge.core.registry import register_ai_provider

logger = get_logger("ai.anthropic")

# Pricing per 1M tokens (Claude Sonnet 4.6, as of 2026-04)
_INPUT_COST_PER_M = 3.00
_OUTPUT_COST_PER_M = 15.00


@dataclass
class _CostTracker:
    """Tracks cumulative AI spend for a job."""

    limit_usd: float = 50.0
    total_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    def record(self, usage) -> None:
        input_cost = (usage.input_tokens / 1_000_000) * _INPUT_COST_PER_M
        output_cost = (usage.output_tokens / 1_000_000) * _OUTPUT_COST_PER_M
        self.total_usd += input_cost + output_cost
        self.total_input_tokens += usage.input_tokens
        self.total_output_tokens += usage.output_tokens

    def check_budget(self) -> None:
        if self.total_usd >= self.limit_usd:
            raise AIError(
                f"AI cost budget exceeded: ${self.total_usd:.2f} >= "
                f"${self.limit_usd:.2f} limit"
            )


class _RateLimiter:
    """Simple token-bucket rate limiter for API calls."""

    def __init__(self, rpm: int = 60):
        self._min_interval = 60.0 / rpm if rpm > 0 else 0
        self._last_call = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_call = time.monotonic()


@register_ai_provider("anthropic")
class AnthropicAIProvider(BaseAIProvider):
    """AI provider using Anthropic's Claude API."""

    def __init__(self, config: dict):
        ai_config = config.get("ai", {}) if isinstance(config, dict) else config
        api_key = ai_config.get("api_key") or ""
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = ai_config.get("model", "claude-sonnet-4-6")
        self._max_tokens = ai_config.get("max_tokens", 4096)
        self._temperature = ai_config.get("temperature", 0.7)
        self._rate_limiter = _RateLimiter(ai_config.get("rate_limit_rpm", 60))
        self._cost = _CostTracker(limit_usd=ai_config.get("cost_limit_per_job_usd", 50.0))

    # ------------------------------------------------------------------
    # BaseAIProvider interface
    # ------------------------------------------------------------------

    def generate(self, prompt: str, context: str, max_tokens: int) -> str:
        """Generate text given a prompt and optional context."""
        user_content = f"{context}\n\n{prompt}" if context else prompt
        return self._call_with_retry(
            self._create_message,
            system=None,
            user_content=user_content,
            max_tokens=max_tokens or self._max_tokens,
        )

    def rewrite(
        self,
        text: str,
        instruction: str,
        max_tokens: int,
        system_context: str = "",
    ) -> str:
        """Rewrite text per instruction.

        system_context is read-only context from the previous chunk — passed
        in the system message so the model can maintain coherence without
        re-rewriting it.
        """
        system = instruction
        if system_context:
            system += (
                "\n\nContext from previous section (DO NOT rewrite this, "
                "it is for reference only):\n---\n"
                f"{system_context}\n---"
            )

        return self._call_with_retry(
            self._create_message,
            system=system,
            user_content=f"---BEGIN REWRITE---\n{text}",
            max_tokens=max_tokens or self._max_tokens,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _create_message(
        self,
        *,
        system: str | None,
        user_content: str,
        max_tokens: int,
    ) -> str:
        self._rate_limiter.acquire()
        self._cost.check_budget()

        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": self._temperature,
            "messages": [{"role": "user", "content": user_content}],
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)
        self._cost.record(response.usage)

        logger.debug(
            "AI call complete",
            model=self._model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_so_far=f"${self._cost.total_usd:.4f}",
        )

        return response.content[0].text

    def _call_with_retry(self, fn, *args, **kwargs) -> str:
        """Retry AI calls 3x with exponential backoff."""
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                return fn(*args, **kwargs)
            except anthropic.RateLimitError:
                wait = 2**attempt * 5  # 5s, 10s, 20s
                logger.warning("Rate limited, retrying", attempt=attempt + 1, wait=wait)
                time.sleep(wait)
            except anthropic.APIError as exc:
                last_exc = exc
                if attempt < 2:
                    wait = 2**attempt * 2  # 2s, 4s
                    logger.warning("API error, retrying", attempt=attempt + 1, error=str(exc))
                    time.sleep(wait)
            except AIError:
                raise  # budget exceeded — don't retry
            except Exception as exc:
                raise AIError(f"Unexpected AI error: {exc}") from exc

        raise AIError(f"AI call failed after 3 attempts: {last_exc}") from last_exc

    @property
    def cost_summary(self) -> dict:
        """Return current cost tracking data."""
        return {
            "total_usd": round(self._cost.total_usd, 4),
            "total_input_tokens": self._cost.total_input_tokens,
            "total_output_tokens": self._cost.total_output_tokens,
            "limit_usd": self._cost.limit_usd,
        }
