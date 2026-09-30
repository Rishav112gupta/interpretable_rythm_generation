from __future__ import annotations

from app.core.config import settings
from app.services.ai.base import LLMProvider

_override: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    if _override is not None:
        return _override
    provider = settings.effective_llm_provider
    if provider == "anthropic":
        from app.services.ai.anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings.llm_api_key, settings.llm_model, settings.llm_timeout_seconds)
    if provider == "openai":
        from app.services.ai.openai_provider import OpenAICompatibleProvider

        return OpenAICompatibleProvider(settings.llm_api_key, settings.llm_model, settings.llm_base_url, settings.llm_timeout_seconds)
    from app.services.ai.mock_provider import MockLLMProvider

    return MockLLMProvider()


def set_llm_provider(provider: LLMProvider | None) -> None:
    """Override the provider (tests, experiments)."""
    global _override
    _override = provider
