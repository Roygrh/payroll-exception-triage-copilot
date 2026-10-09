"""OpenAI-compatible chat completions adapter (Groq, OpenAI, Ollama, others; ADR-016).

Uses plain HTTP (httpx) against `{base_url}/chat/completions` so that any
OpenAI-compatible endpoint works by configuration. Structured output uses
`response_format: json_schema` (strict when the provider supports it) and
falls back to `json_object` plus the schema in the prompt when configured.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from payroll_triage.llm.v1.interface import (
    ADAPTER_VERSION,
    LLMError,
    LLMRequest,
    LLMResponse,
    Usage,
)
from payroll_triage.llm.v1.pacing import (
    Pacer,
    call_with_retries,
    extract_rate_limit,
    parse_retry_after,
)

JSON_MODES = ("json_schema", "json_object")


class OpenAICompatibleAdapter:
    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: str | None,
        model: str,
        rpm: int = 30,
        max_attempts: int = 5,
        timeout_seconds: float = 60.0,
        json_mode: str = "json_schema",
        reasoning_effort: str | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
    ) -> None:
        if json_mode not in JSON_MODES:
            raise ValueError(f"json_mode must be one of {JSON_MODES}")
        self.provider = provider
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.json_mode = json_mode
        self.reasoning_effort = reasoning_effort
        self.max_attempts = max_attempts
        self._sleep = sleep
        self._pacer = Pacer(rpm, sleep=sleep)
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(
            base_url=self.base_url, headers=headers, timeout=timeout_seconds, transport=transport
        )
        self.last_rate_limit: dict[str, str] = {}

    # ---------- request building ----------

    def _body(self, request: LLMRequest) -> dict[str, Any]:
        messages: list[dict[str, str]] = [{"role": "system", "content": request.system}]
        for m in request.messages:
            messages.append({"role": m.role, "content": m.content})
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
        }
        if request.response_schema is not None:
            if self.json_mode == "json_schema":
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.schema_name,
                        "strict": True,
                        "schema": request.response_schema,
                    },
                }
            else:
                body["response_format"] = {"type": "json_object"}
                messages[0]["content"] += (
                    "\n\nRespond with a single JSON object that conforms to this JSON schema:\n"
                    + json.dumps(request.response_schema)
                )
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        return body

    # ---------- call ----------

    def _once(self, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        try:
            response = self._client.post("/chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise LLMError(f"{self.provider}: request timed out", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.provider}: transport error: {exc}", retryable=True) from exc
        rate = extract_rate_limit(response.headers)
        self.last_rate_limit = rate
        if response.status_code == 429:
            raise LLMError(
                f"{self.provider}: rate limited (429)",
                retryable=True,
                status=429,
                retry_after=parse_retry_after(response.headers),
            )
        if response.status_code >= 500:
            raise LLMError(
                f"{self.provider}: server error {response.status_code}",
                retryable=True,
                status=response.status_code,
            )
        if response.status_code >= 400:
            detail = _error_detail(response)
            raise LLMError(
                f"{self.provider}: request rejected ({response.status_code}): {detail}",
                retryable=False,
                status=response.status_code,
            )
        try:
            return response.json(), rate
        except ValueError as exc:
            raise LLMError(f"{self.provider}: non-JSON response body", retryable=False) from exc

    def complete(self, request: LLMRequest) -> LLMResponse:
        body = self._body(request)
        started = time.monotonic()
        self._pacer.wait()
        (data, rate), attempts = call_with_retries(
            lambda: self._once(body), max_attempts=self.max_attempts, sleep=self._sleep
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        text = _message_text(data, self.provider)
        parsed: dict[str, Any] | None = None
        if request.response_schema is not None:
            parsed = _parse_json_object(text, self.provider)
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            parsed=parsed,
            provider=self.provider,
            model=str(data.get("model") or self.model),
            adapter_version=ADAPTER_VERSION,
            usage=Usage(
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
            ),
            latency_ms=latency_ms,
            rate_limit=rate,
            attempts=attempts,
        )


def _error_detail(response: httpx.Response) -> str:
    try:
        err = response.json().get("error", {})
        return str(err.get("message") or err)[:300]
    except ValueError:
        return response.text[:300]


def _message_text(data: dict[str, Any], provider: str) -> str:
    try:
        choice = data["choices"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"{provider}: response has no choices", retryable=False) from exc
    finish = choice.get("finish_reason")
    if finish == "length":
        raise LLMError(f"{provider}: output truncated (finish_reason=length)", retryable=False)
    content = (choice.get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise LLMError(f"{provider}: empty message content", retryable=False)
    return content


def _parse_json_object(text: str, provider: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:]
    try:
        parsed = json.loads(candidate)
    except ValueError as exc:
        raise LLMError(f"{provider}: output is not valid JSON", retryable=False) from exc
    if not isinstance(parsed, dict):
        raise LLMError(f"{provider}: output JSON is not an object", retryable=False)
    return parsed
