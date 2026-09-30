"""Anthropic (Claude) provider using the official `anthropic` Python SDK."""

from __future__ import annotations

import time
from typing import Any

import anthropic

from app.core.errors import LLMError
from app.services.ai.base import LLMProvider, LLMResult
from app.services.ai.schemas import extract_json_object

DEFAULT_MODEL = "claude-opus-5-5"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "", timeout: float = 120.0) -> None:
        if not api_key:
            raise LLMError("LLM_API_KEY is not set for the Anthropic provider.")
        self.model = model or DEFAULT_MODEL
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)

    def complete_json(
        self,
        *,
        task: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        context: dict[str, Any],
        max_tokens: int = 16000,
    ) -> LLMResult:
        started = time.monotonic()
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=max(max_tokens, 16000),
                system=system,
                messages=[{"role": "user", "content": user}],
                # Structured outputs: the response text is guaranteed to be JSON matching `schema`.
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
                # Server-side fallback if the primary model declines a request.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as exc:
            raise LLMError("Anthropic rejected the API key (check LLM_API_KEY).") from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMError("The Anthropic API key lacks permission for this model.") from exc
        except anthropic.NotFoundError as exc:
            raise LLMError(f"Anthropic model '{self.model}' was not found (check LLM_MODEL).") from exc
        except anthropic.BadRequestError as exc:
            raise LLMError(f"Anthropic rejected the request: {exc.message}") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Anthropic rate limit reached. Try again shortly.", transient=True) from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error ({exc.status_code}).", transient=exc.status_code >= 500) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Could not reach the Anthropic API (network error).", transient=True) from exc

        if response.stop_reason == "refusal":
            raise LLMError("The AI declined to generate this content. Rephrase the topic and try again.")
        if response.stop_reason == "max_tokens":
            raise LLMError("The AI response was cut off (max tokens reached).", transient=True)

        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        data = extract_json_object(text)
        usage = {}
        if getattr(response, "usage", None) is not None:
            usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
        return LLMResult(
            data=data,
            provider=self.name,
            model=getattr(response, "model", self.model) or self.model,
            duration_ms=int((time.monotonic() - started) * 1000),
            usage=usage,
        )
