"""Abstract base class for AI providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseAIProvider(ABC):
    """Generates or rewrites text content via an AI model."""

    @abstractmethod
    def generate(self, prompt: str, context: str, max_tokens: int) -> str:
        """Generate text given a prompt and context."""

    @abstractmethod
    def rewrite(
        self, text: str, instruction: str, max_tokens: int, system_context: str = ""
    ) -> str:
        """Rewrite text according to instruction.

        system_context is read-only context from a previous chunk — it is
        passed as system context to the model, NOT as text to rewrite.
        """
