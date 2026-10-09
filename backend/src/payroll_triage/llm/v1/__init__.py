"""LLM adapter interface v1 (ADR-002, ADR-016).

`LLMAdapter.complete(request) -> LLMResponse` is the only way the graph talks to
a model. Implementations: `OpenAICompatibleAdapter` (Groq, OpenAI, a local
Ollama server, any OpenAI-compatible endpoint) and `AnthropicAdapter`
(optional). The adapter never computes payroll facts, never writes to the
database and never returns templated text: a failure is an `LLMError`.
"""

from payroll_triage.llm.v1.factory import build_adapter
from payroll_triage.llm.v1.interface import (
    ADAPTER_VERSION,
    LLMAdapter,
    LLMError,
    LLMRequest,
    LLMResponse,
    Message,
    Usage,
)

__all__ = [
    "ADAPTER_VERSION",
    "LLMAdapter",
    "LLMError",
    "LLMRequest",
    "LLMResponse",
    "Message",
    "Usage",
    "build_adapter",
]
