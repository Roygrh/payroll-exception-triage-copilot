"""Versioned adapter interface (v1). A breaking change produces `llm/v2`, not an edit here."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

ADAPTER_VERSION = "v1"


@dataclass(frozen=True)
class Message:
    role: str  # "user" or "assistant"
    content: str


@dataclass(frozen=True)
class LLMRequest:
    system: str
    messages: tuple[Message, ...]
    response_schema: dict[str, Any] | None = None
    schema_name: str = "response"
    max_output_tokens: int = 1200
    temperature: float = 0.0
    metadata: dict[str, str] = field(default_factory=dict)  # case id, node, rule ids (tracing)


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class LLMResponse:
    text: str
    parsed: dict[str, Any] | None
    provider: str
    model: str
    adapter_version: str
    usage: Usage
    latency_ms: int
    rate_limit: dict[str, str] = field(default_factory=dict)  # provider headers, no secrets
    attempts: int = 1

    def summary(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "adapter_version": self.adapter_version,
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "latency_ms": self.latency_ms,
            "attempts": self.attempts,
        }


class LLMError(Exception):
    """Any failure of a model call: transport, rate limit, provider error, unparsable output."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status = status
        self.retry_after = retry_after


@runtime_checkable
class LLMAdapter(Protocol):
    provider: str
    model: str

    def complete(self, request: LLMRequest) -> LLMResponse: ...
