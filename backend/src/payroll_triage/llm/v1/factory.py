"""Build the configured adapter from settings (provider and model by configuration, ADR-002)."""

from __future__ import annotations

from payroll_triage.config import ConfigError, Settings
from payroll_triage.llm.v1.interface import LLMAdapter

OPENAI_COMPATIBLE_PROVIDERS = ("groq", "openai", "ollama", "openai_compatible")


def build_adapter(settings: Settings) -> LLMAdapter:
    provider = settings.llm_provider
    if provider == "anthropic":
        from payroll_triage.llm.v1.anthropic_adapter import AnthropicAdapter

        return AnthropicAdapter(
            api_key=settings.require_llm_key(),
            model=settings.llm_model,
            rpm=settings.llm_rpm,
            max_attempts=settings.llm_max_attempts,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        from payroll_triage.llm.v1.openai_compatible import OpenAICompatibleAdapter

        api_key = None if provider == "ollama" else settings.require_llm_key()
        return OpenAICompatibleAdapter(
            provider=provider,
            base_url=settings.llm_base_url,
            api_key=api_key,
            model=settings.llm_model,
            rpm=settings.llm_rpm,
            max_attempts=settings.llm_max_attempts,
            timeout_seconds=settings.llm_timeout_seconds,
            json_mode=settings.llm_json_mode,
            reasoning_effort=settings.llm_reasoning_effort,
        )
    raise ConfigError(
        f"unknown PTC_LLM_PROVIDER {provider!r}; expected one of "
        f"{OPENAI_COMPATIBLE_PROVIDERS + ('anthropic',)}"
    )
