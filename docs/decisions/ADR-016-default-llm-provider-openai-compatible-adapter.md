# ADR-016: Default LLM is gpt-oss-20b on GroqCloud through an OpenAI-compatible adapter

Status: Accepted (supersedes ADR-002 on the provider choice; the adapter interface decision of ADR-002 stands)
Date: 2026-10-08

## Context

ADR-002 chose Anthropic as the single Phase 1 provider behind a versioned adapter. Anyone who clones the repository should be able to run the demo without a payment method. GroqCloud offers a free tier (no credit card) that serves the open-weights model `openai/gpt-oss-20b` through an OpenAI-compatible chat completions endpoint with JSON schema structured outputs. The same wire format is served by OpenAI, by a local Ollama server and by most hosted inference providers, so one adapter implementation covers many endpoints by configuration.

## Decision

- **Default provider and model:** `PTC_LLM_PROVIDER=groq`, `PTC_LLM_BASE_URL=https://api.groq.com/openai/v1`, `PTC_LLM_MODEL=openai/gpt-oss-20b`, key in `GROQ_API_KEY`. The defaults live in `backend/src/payroll_triage/config.py` and in the root `.env.example`.
- **One OpenAI-compatible adapter** (`llm/v1/openai_compatible.py`) implemented over plain HTTP (httpx) against `{base_url}/chat/completions`. It works with other endpoints by configuration only: OpenAI (`PTC_LLM_PROVIDER=openai`, `OPENAI_API_KEY`), a local Ollama server (`PTC_LLM_PROVIDER=ollama`, `PTC_LLM_BASE_URL=http://localhost:11434/v1`, no key) or any other compatible endpoint (`PTC_LLM_PROVIDER=openai_compatible` with `PTC_LLM_API_KEY`). Anthropic remains available as an optional provider behind the same v1 interface (`llm/v1/anthropic_adapter.py`, `PTC_LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`).
- **Structured output:** `response_format` of type `json_schema` with `strict: true` (supported by gpt-oss-20b on Groq, verified on the provider's structured outputs documentation on 2026-10-08); `PTC_LLM_JSON_MODE=json_object` is the fallback for endpoints without schema support, in which case the schema is appended to the system prompt and code still validates the output.
- **Configuration:** the single root `.env` (template `.env.example`), loaded by the backend when run from `backend/` with uv (python-dotenv, never overriding the process environment) and passed to the API container by compose `env_file`. `DATABASE_URL` keeps the template value. No `backend/.env`.
- **Free-tier rate limits:** client-side pacing with a minimum interval between call starts (`PTC_LLM_RPM`, default 30) and retry with exponential backoff and jitter on HTTP 429 and 5xx, honoring `retry-after` (`PTC_LLM_MAX_ATTEMPTS`, default 5). The adapter records the provider's rate-limit headers (`x-ratelimit-limit-requests`, `x-ratelimit-limit-tokens`, `x-ratelimit-remaining-requests`, `x-ratelimit-remaining-tokens`, `x-ratelimit-reset-requests`, `x-ratelimit-reset-tokens`, `retry-after`) on every response so a run can report the live limits. `reasoning_effort=low` is sent to Groq by default so that structured outputs stay within the per-minute token budget.
- **Limits verified on 2026-10-08:** the provider's public rate-limits page lists `openai/gpt-oss-20b` at 30 requests per minute, 1,000 requests per day, 8,000 tokens per minute and 200,000 tokens per day in its base (developer plan) table, and states that free-tier values are shown on the account's limits page. The limits in force for the author's account are confirmed from the response headers of the first successful call (recorded in the iteration log).
- **Secrets:** keys are never printed or logged; `Settings.redacted()` is the only representation of the configuration that may be output. A missing key is a clear error naming the variable, not a fallback.

## Consequences

- Anyone can run the demo with a free account. Switching providers is a configuration change; the graph, prompts and validators do not change.
- The prompts and the tier 2 judge are tuned on a 20-billion-parameter open model; the evaluation gate (ADR-003) measures that model. A provider or model change re-baselines the gate.
- Free-tier budgets bound the demo: three structured calls per case, about 3,000 to 5,000 tokens per case; the pacing keeps a week ingest under the per-minute limits at the cost of wall-clock time.
- The `openai` SDK is not a dependency; `anthropic` is installed for the optional adapter. The Phase 2 gateway (fallback, cost and latency control) still sits behind the same v1 interface.
- ADR-002's "Anthropic" wording in the brief, the architecture overview and the plan is updated to reference this record.

### Update of 2026-10-09 (first real run)

- **Live limits confirmed** from the response headers of the first successful call (2026-10-08, author's account): 1,000 requests per day and 8,000 tokens per minute for `openai/gpt-oss-20b`. The daily token limit is not reported in the headers.
- **Measured cost:** the SC-03 showcase used about 10,000 tokens per case across three calls (about 3,100 to 3,500 input tokens each), twice the estimate above and more than one minute's token budget, so the third call needed a retry. ADR-018 (Proposed) reduces calls and input size; Iteration 2b targets at most 5,000 tokens per MEAL_PERIOD case.
- **The GroqCloud free tier stays the default provider** so that anyone can run the repository without a payment method. Anthropic and OpenAI remain optional providers by configuration. Their APIs are billed per use and are separate from consumer chat subscriptions: a chat subscription does not include API access.
- **A local model through Ollama stays a Phase 2 option (P2.I7).** The endpoint works by configuration, but it is not tested or supported in Phase 1, and the hardware needed to run a model of adequate quality locally is not yet known.
