"""Optional Anthropic adapter behind the same v1 interface (ADR-002, ADR-016).

Structured output is obtained by forcing a single tool whose input schema is
the response schema; the tool input is the parsed object. The SDK is imported
lazily so that the default (OpenAI-compatible) configuration does not need it.
"""

from __future__ import annotations

import time
from typing import Any

from payroll_triage.llm.v1.interface import (
    ADAPTER_VERSION,
    LLMError,
    LLMRequest,
    LLMResponse,
    Usage,
)
from payroll_triage.llm.v1.pacing import Pacer, call_with_retries, extract_rate_limit


class AnthropicAdapter:
    provider = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        rpm: int = 30,
        max_attempts: int = 5,
        timeout_seconds: float = 60.0,
        sleep=time.sleep,
    ) -> None:
        import anthropic

        self.model = model
        self.max_attempts = max_attempts
        self._sleep = sleep
        self._pacer = Pacer(rpm, sleep=sleep)
        self._errors = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_seconds, max_retries=0)
        self.last_rate_limit: dict[str, str] = {}

    def _once(self, request: LLMRequest) -> tuple[Any, dict[str, str]]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "system": request.system,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        if request.response_schema is not None:
            kwargs["tools"] = [
                {
                    "name": request.schema_name,
                    "description": "Return the structured response.",
                    "input_schema": request.response_schema,
                }
            ]
            kwargs["tool_choice"] = {"type": "tool", "name": request.schema_name}
        try:
            raw = self._client.messages.with_raw_response.create(**kwargs)
        except self._errors.RateLimitError as exc:
            retry_after = None
            try:
                retry_after = float(exc.response.headers.get("retry-after", ""))
            except (ValueError, AttributeError):
                pass
            raise LLMError(
                "anthropic: rate limited (429)", retryable=True, status=429, retry_after=retry_after
            ) from exc
        except self._errors.APIStatusError as exc:
            raise LLMError(
                f"anthropic: status {exc.status_code}",
                retryable=exc.status_code >= 500,
                status=exc.status_code,
            ) from exc
        except self._errors.APIConnectionError as exc:
            raise LLMError("anthropic: connection error", retryable=True) from exc
        rate = extract_rate_limit(raw.headers)
        self.last_rate_limit = rate
        return raw.parse(), rate

    def complete(self, request: LLMRequest) -> LLMResponse:
        started = time.monotonic()
        self._pacer.wait()
        (message, rate), attempts = call_with_retries(
            lambda: self._once(request), max_attempts=self.max_attempts, sleep=self._sleep
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        parsed: dict[str, Any] | None = None
        text = ""
        for block in message.content:
            if getattr(block, "type", "") == "tool_use" and request.response_schema is not None:
                parsed = dict(block.input)
            elif getattr(block, "type", "") == "text":
                text += block.text
        if request.response_schema is not None and parsed is None:
            raise LLMError("anthropic: no structured tool output returned", retryable=False)
        usage = getattr(message, "usage", None)
        return LLMResponse(
            text=text,
            parsed=parsed,
            provider=self.provider,
            model=str(getattr(message, "model", self.model)),
            adapter_version=ADAPTER_VERSION,
            usage=Usage(
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
            ),
            latency_ms=latency_ms,
            rate_limit=rate,
            attempts=attempts,
        )
