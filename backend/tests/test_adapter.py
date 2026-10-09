"""LLM adapter v1: OpenAI-compatible transport, pacing, retries and configuration."""

from __future__ import annotations

import json

import httpx
import pytest

from payroll_triage import config
from payroll_triage.llm.v1 import LLMError, LLMRequest, Message, build_adapter
from payroll_triage.llm.v1.openai_compatible import OpenAICompatibleAdapter
from payroll_triage.llm.v1.pacing import Pacer, backoff_delay, call_with_retries

SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def _request(schema=SCHEMA) -> LLMRequest:
    return LLMRequest(
        system="sys", messages=(Message("user", "hi"),), response_schema=schema, schema_name="t"
    )


def _completion(content: str, finish="stop") -> dict:
    return {
        "model": "test-model",
        "choices": [
            {"message": {"role": "assistant", "content": content}, "finish_reason": finish}
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3},
    }


def _adapter(handler, **kw) -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(
        provider="groq",
        base_url="https://example.invalid/openai/v1",
        api_key="not-a-real-key",
        model="test-model",
        rpm=0,
        max_attempts=kw.pop("max_attempts", 3),
        transport=httpx.MockTransport(handler),
        sleep=lambda s: None,
        **kw,
    )


def test_structured_request_body_and_parsed_response():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=_completion('{"ok": true}'),
            headers={"x-ratelimit-remaining-requests": "29", "x-ratelimit-limit-tokens": "8000"},
        )

    adapter = _adapter(handler, reasoning_effort="low")
    response = adapter.complete(_request())
    assert seen["url"].endswith("/openai/v1/chat/completions")
    assert seen["auth"] == "Bearer not-a-real-key"
    body = seen["body"]
    assert body["model"] == "test-model"
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert body["reasoning_effort"] == "low"
    assert response.parsed == {"ok": True}
    assert response.usage.input_tokens == 12 and response.usage.output_tokens == 3
    assert response.rate_limit == {
        "x-ratelimit-remaining-requests": "29",
        "x-ratelimit-limit-tokens": "8000",
    }
    assert response.adapter_version == "v1" and response.provider == "groq"


def test_json_object_mode_puts_schema_in_the_system_prompt():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion('```json\n{"ok": false}\n```'))

    adapter = _adapter(handler, json_mode="json_object")
    response = adapter.complete(_request())
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert "JSON schema" in seen["body"]["messages"][0]["content"]
    assert response.parsed == {"ok": False}


def test_rate_limit_then_success_retries_with_retry_after():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                429, json={"error": {"message": "slow down"}}, headers={"retry-after": "2"}
            )
        return httpx.Response(200, json=_completion('{"ok": true}'))

    response = _adapter(handler).complete(_request())
    assert response.attempts == 2 and response.parsed == {"ok": True}


def test_rate_limit_exhausts_attempts():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "slow down"}})

    with pytest.raises(LLMError) as exc:
        _adapter(handler, max_attempts=2).complete(_request())
    assert exc.value.retryable and exc.value.status == 429


def test_client_errors_are_not_retried_and_never_templated():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"message": "bad schema"}})

    with pytest.raises(LLMError, match="bad schema"):
        _adapter(handler).complete(_request())
    assert calls["n"] == 1


@pytest.mark.parametrize(
    "content,finish,match",
    [
        ("not json", "stop", "not valid JSON"),
        ("[1, 2]", "stop", "not an object"),
        ('{"ok": true}', "length", "truncated"),
        ("", "stop", "empty"),
    ],
)
def test_bad_outputs_raise(content, finish, match):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion(content, finish))

    with pytest.raises(LLMError, match=match):
        _adapter(handler).complete(_request())


def test_server_error_then_success():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json=_completion('{"ok": true}'))

    assert _adapter(handler).complete(_request()).attempts == 3


def test_pacer_spaces_calls():
    slept = []
    pacer = Pacer(rpm=60, sleep=slept.append)
    assert pacer.wait() == 0.0
    waited = pacer.wait()
    assert 0.9 < waited <= 1.0 and slept and abs(slept[0] - waited) < 1e-9


def test_backoff_honors_retry_after_and_caps():
    assert 2.0 <= backoff_delay(1, 1.0, 60.0, 2.0) <= 2.5
    assert backoff_delay(10, 1.0, 60.0, None) == 60.0
    assert 1.0 <= backoff_delay(1, 1.0, 60.0, None) <= 2.0


def test_call_with_retries_only_on_retryable():
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise LLMError("again", retryable=True)
        return "done"

    assert call_with_retries(flaky, max_attempts=3, sleep=lambda s: None) == ("done", 2)
    with pytest.raises(LLMError):
        call_with_retries(
            lambda: (_ for _ in ()).throw(LLMError("no", retryable=False)),
            max_attempts=3,
            sleep=lambda s: None,
        )


def test_settings_defaults_and_key_resolution(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("PTC_LLM_PROVIDER=groq\nGROQ_API_KEY=value-for-test\n", encoding="utf-8")
    for var in ("PTC_LLM_PROVIDER", "GROQ_API_KEY", "PTC_LLM_BASE_URL", "PTC_LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(
        config, "load_env_file", lambda path=None: config.load_dotenv(env, override=False) and env
    )
    s = config.get_settings()
    assert s.llm_provider == "groq"
    assert s.llm_base_url == "https://api.groq.com/openai/v1"
    assert s.llm_model == "openai/gpt-oss-20b"
    assert s.llm_api_key == "value-for-test"
    assert s.llm_reasoning_effort == "low"
    assert s.redacted()["llm_api_key"] == "set"
    assert "value-for-test" not in json.dumps(s.redacted())
    assert s.redacted()["database_url"] == "postgresql://ptc:***@localhost:5432/ptc"
    adapter = build_adapter(s)
    assert isinstance(adapter, OpenAICompatibleAdapter) and adapter.provider == "groq"


def test_missing_key_is_a_clear_error_without_the_value(monkeypatch):
    monkeypatch.setattr(config, "load_env_file", lambda path=None: None)
    monkeypatch.setenv("PTC_LLM_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("PTC_LLM_API_KEY", raising=False)
    s = config.get_settings()
    assert s.llm_api_key is None
    with pytest.raises(config.ConfigError, match="GROQ_API_KEY is not set"):
        build_adapter(s)


def test_ollama_needs_no_key_and_other_endpoints_work_by_configuration(monkeypatch):
    monkeypatch.setattr(config, "load_env_file", lambda path=None: None)
    monkeypatch.setenv("PTC_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("PTC_LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("PTC_LLM_MODEL", "some-local-model")
    monkeypatch.delenv("PTC_LLM_REASONING_EFFORT", raising=False)
    s = config.get_settings()
    adapter = build_adapter(s)
    assert isinstance(adapter, OpenAICompatibleAdapter)
    assert adapter.base_url == "http://localhost:11434/v1" and adapter.reasoning_effort is None
    assert "Authorization" not in adapter._client.headers
