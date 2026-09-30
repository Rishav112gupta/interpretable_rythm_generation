"""OpenAI-compatible chat completions provider (raw HTTP).

Works with OpenAI and with any service exposing the same
`/chat/completions` API (set LLM_BASE_URL). Uses JSON-schema structured output.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.errors import LLMError
from app.services.ai.base import LLMProvider, LLMResult
from app.services.ai.schemas import extract_json_object


class OpenAICompatibleProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float = 120.0) -> None:
        if not api_key:
            raise LLMError("LLM_API_KEY is not set for the OpenAI-compatible provider.")
        if not model:
            raise LLMError("LLM_MODEL must be set for the OpenAI-compatible provider.")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self.timeout = timeout

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
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {"name": task, "schema": schema, "strict": True}},
            "max_completion_tokens": max_tokens,
        }
        started = time.monotonic()
        try:
            resp = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=self._headers, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise LLMError("Could not reach the LLM API (network error).", transient=True) from exc
        if resp.status_code == 401:
            raise LLMError("The LLM provider rejected the API key (check LLM_API_KEY).")
        if resp.status_code == 429:
            raise LLMError("LLM rate limit reached. Try again shortly.", transient=True)
        if resp.status_code >= 400:
            raise LLMError(f"LLM API error ({resp.status_code}).", transient=resp.status_code >= 500)
        try:
            payload = resp.json()
            choice = payload["choices"][0]
            text = choice["message"].get("content") or ""
        except (ValueError, KeyError, IndexError) as exc:
            raise LLMError("Unexpected response shape from the LLM API.") from exc
        if choice["message"].get("refusal"):
            raise LLMError("The AI declined to generate this content. Rephrase and try again.")
        return LLMResult(
            data=extract_json_object(text),
            provider=self.name,
            model=payload.get("model", self.model),
            duration_ms=int((time.monotonic() - started) * 1000),
            usage=payload.get("usage", {}),
        )
