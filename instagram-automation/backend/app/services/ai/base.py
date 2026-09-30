"""LLM provider abstraction.

The rest of the application only talks to `LLMProvider.complete_json()`.
Swapping providers (Anthropic, OpenAI-compatible, mock) is a configuration
change, never a code change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResult:
    data: dict[str, Any]
    provider: str
    model: str
    duration_ms: int
    usage: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def complete_json(
        self,
        *,
        task: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        context: dict[str, Any],
        max_tokens: int = 4000,
    ) -> LLMResult:
        """Run one structured-output request.

        task:    "post" | "ideas" | "competitor_analysis" (lets the mock produce realistic data)
        schema:  JSON Schema the response must follow
        context: the structured inputs the prompt was built from (used by the mock only)
        """
