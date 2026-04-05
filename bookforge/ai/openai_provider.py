"""OpenAI AI provider — GPT API implementation.

Second AI backend per IMPLEMENTATION.md Phase K. Implements BaseAIProvider
using the OpenAI SDK. Supports GPT-4o and GPT-4-turbo models.
"""

from __future__ import annotations

import time
import threading

import openai

from bookforge.ai.base import BaseAIProvider
from bookforge.core.exceptions import AIError
from bookforge.core.logging import get_logger
from bookforge.core.registry import register_ai_provider

logger = get_logger("ai.openai")


class _RateLimiter:
    """Simple rate limiter for API calls."""

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


@register_ai_provider("openai")
class OpenAIProvider(BaseAIProvider):
    """AI provider using OpenAI's GPT API."""

    def __init__(self, config: dict):
        ai_config = config.get("ai", {}) if isinstance(config, dict) else config
        api_key = ai_config.get("api_key") or ""
        self._client = openai.OpenAI(api_key=api_key)
        self._model = ai_config.get("model", "gpt-4o")
        self._max_tokens = ai_config.get("max_tokens", 4096)
        self._temperature = ai_config.get("temperature", 0.7)
        self._rate_limiter = _RateLimiter(ai_config.get("rate_limit_rpm", 60))

    def generate(self, prompt: str, context: str, max_tokens: int) -> str:
        """Generate text given a prompt and context."""
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": prompt})

        return self._call_with_retry(messages, max_tokens or self._max_tokens)

    def rewrite(
        self,
        text: str,
        instruction: str,
        max_tokens: int,
        system_context: str = "",
    ) -> str:
        """Rewrite text per instruction."""
        system = instruction
        if system_context:
            system += (
                "\n\nContext from previous section (DO NOT rewrite this, "
                "it is for reference only):\n---\n"
                f"{system_context}\n---"
            )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"---BEGIN REWRITE---\n{text}"},
        ]

        return self._call_with_retry(messages, max_tokens or self._max_tokens)

    def _call_with_retry(self, messages: list[dict], max_tokens: int) -> str:
        """Retry API calls 3x with exponential backoff."""
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                self._rate_limiter.acquire()
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=self._temperature,
                )
                return response.choices[0].message.content or ""
            except openai.RateLimitError:
                wait = 2**attempt * 5
                logger.warning("Rate limited, retrying", attempt=attempt + 1, wait=wait)
                time.sleep(wait)
            except openai.APIError as exc:
                last_exc = exc
                if attempt < 2:
                    wait = 2**attempt * 2
                    logger.warning("API error, retrying", attempt=attempt + 1, error=str(exc))
                    time.sleep(wait)
            except Exception as exc:
                raise AIError(f"Unexpected AI error: {exc}") from exc

        raise AIError(f"AI call failed after 3 attempts: {last_exc}") from last_exc
