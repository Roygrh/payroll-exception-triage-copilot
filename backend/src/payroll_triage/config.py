"""Runtime configuration from the single root `.env` (ADR-016, ADR-017).

The root `.env` is loaded once, without overriding variables already present in
the process, so docker compose (`env_file`) and `uv run` from `backend/` see the
same values. Secrets are never logged or printed: `Settings.redacted()` is the
only representation meant for output.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from payroll_triage.paths import repo_root

ENV_FILE = ".env"

PROVIDER_KEY_VARS: dict[str, str | None] = {
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "ollama": None,
    "anthropic": "ANTHROPIC_API_KEY",
}

DEFAULTS = {
    "PTC_LLM_PROVIDER": "groq",
    "PTC_LLM_BASE_URL": "https://api.groq.com/openai/v1",
    "PTC_LLM_MODEL": "openai/gpt-oss-20b",
    "PTC_LLM_RPM": "30",
    "PTC_LLM_MAX_ATTEMPTS": "5",
    "PTC_LLM_TIMEOUT_SECONDS": "60",
    "PTC_LLM_MAX_OUTPUT_TOKENS": "1200",
    "PTC_LLM_JSON_MODE": "json_schema",
    "PTC_LLM_REASONING_EFFORT": "",
    "PTC_EMBEDDING_MODEL": "BAAI/bge-small-en-v1.5",
    "PTC_EMBEDDING_DIM": "384",
    "DATABASE_URL": "postgresql://ptc:ptc@localhost:5432/ptc",
}


class ConfigError(RuntimeError):
    pass


def load_env_file(path: Path | None = None) -> Path | None:
    """Load the root .env if present. Returns the path loaded, or None."""
    path = path or repo_root() / ENV_FILE
    if path.is_file():
        load_dotenv(path, override=False)
        return path
    return None


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str | None
    llm_rpm: int
    llm_max_attempts: int
    llm_timeout_seconds: float
    llm_max_output_tokens: int
    llm_json_mode: str
    llm_reasoning_effort: str | None
    embedding_model: str
    embedding_dim: int
    database_url: str

    def redacted(self) -> dict[str, object]:
        return {
            "llm_provider": self.llm_provider,
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "llm_api_key": "set" if self.llm_api_key else "missing",
            "llm_rpm": self.llm_rpm,
            "llm_json_mode": self.llm_json_mode,
            "llm_reasoning_effort": self.llm_reasoning_effort,
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
            "database_url": _redact_url(self.database_url),
        }

    def require_llm_key(self) -> str:
        """The configured provider's key, or a clear error naming the variable (never the value)."""
        var = PROVIDER_KEY_VARS.get(self.llm_provider)
        if var is None and self.llm_provider in PROVIDER_KEY_VARS:
            return self.llm_api_key or "none"
        if not self.llm_api_key:
            name = var or "PTC_LLM_API_KEY"
            raise ConfigError(
                f"{name} is not set. Add it to the root .env (see .env.example); "
                f"the provider is {self.llm_provider!r}."
            )
        return self.llm_api_key


def _redact_url(url: str) -> str:
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        creds, host = rest.rsplit("@", 1)
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return url


def _get(name: str) -> str:
    return os.environ.get(name, DEFAULTS.get(name, "")).strip()


def get_settings() -> Settings:
    load_env_file()
    provider = _get("PTC_LLM_PROVIDER").lower() or "groq"
    explicit = os.environ.get("PTC_LLM_API_KEY", "").strip() or None
    key_var = PROVIDER_KEY_VARS.get(provider, "PTC_LLM_API_KEY")
    provider_key = os.environ.get(key_var, "").strip() if key_var else ""
    api_key = explicit or provider_key or None
    # Groq's gpt-oss models accept a reasoning effort; low keeps structured outputs short
    # under the free-tier token budget. Other providers get it only when set explicitly.
    effort = _get("PTC_LLM_REASONING_EFFORT") or ("low" if provider == "groq" else "")
    return Settings(
        llm_provider=provider,
        llm_base_url=_get("PTC_LLM_BASE_URL"),
        llm_model=_get("PTC_LLM_MODEL"),
        llm_api_key=api_key,
        llm_rpm=int(_get("PTC_LLM_RPM")),
        llm_max_attempts=int(_get("PTC_LLM_MAX_ATTEMPTS")),
        llm_timeout_seconds=float(_get("PTC_LLM_TIMEOUT_SECONDS")),
        llm_max_output_tokens=int(_get("PTC_LLM_MAX_OUTPUT_TOKENS")),
        llm_json_mode=_get("PTC_LLM_JSON_MODE"),
        llm_reasoning_effort=effort or None,
        embedding_model=_get("PTC_EMBEDDING_MODEL"),
        embedding_dim=int(_get("PTC_EMBEDDING_DIM")),
        database_url=_get("DATABASE_URL"),
    )
