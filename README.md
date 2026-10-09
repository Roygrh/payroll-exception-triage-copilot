# Payroll Exception Triage Copilot

A reference implementation of exception triage for entertainment production payroll.

When a crew timecard trips a rule of the collective agreement (late meal, extended day, short rest, incomplete punches, a deal memo rate below scale, overdue eligibility paperwork), a deterministic rule engine detects the finding and computes the facts. An LLM then explains the finding with verifiable citations to the exact agreement passage and deal memo, proposes the resolution and drafts the return message. A human approver decides. Deterministic code executes the decision and writes an append-only audit trail. An evaluation gate measures the LLM against known ground truth before any version ships.

Everything in this repository is synthetic: the agreement, the rates, the crew, the productions and the timecards. No real company, product, union or guild is named or quoted.

## Status

Phase 1, Iteration 2 (vertical slice MEAL_PERIOD end to end) built: rule engine and code-owned policy, PostgreSQL 16 with pgvector and migrations, corpus ingestion with a local embedding model and hybrid retrieval, LLM adapter v1 (OpenAI-compatible; default gpt-oss-20b on the GroqCloud free tier, ADR-016), LangGraph state machine with citation validation and a durable human checkpoint, FastAPI API for demo steps 1 to 3. No UI, evaluation harness or tracing yet (Iterations 3 to 6). See `docs/progress/current-state.md` for the handoff and `docs/planning/current-plan.md` for the next steps.

## Quick start

Requirements: uv (ADR-015), Docker, a free GroqCloud API key (no credit card; any other OpenAI-compatible endpoint or Anthropic works by configuration, ADR-016).

```
cp .env.example .env                       # then paste your key into GROQ_API_KEY
docker compose -f deployment/docker-compose.yml up -d db
cd backend
uv sync
uv run ptc migrate                         # tables, audit trigger, LangGraph checkpoint tables
uv run ptc seed                            # 22 timecards, 10 deal memos
uv run ptc ingest-corpus                   # downloads the embedding model once (about 67 MB)
uv run ptc smoke-llm                       # one real call; prints the provider's rate limit headers
uv run ptc showcase --decision return      # SC-03 end to end: detect, retrieve, explain, propose, draft,
                                           # validate, pause, resume with a decision, execute, audit
uv run ptc serve                           # API on http://127.0.0.1:8000/docs
uv run pytest                              # 175 tests (integration tests use the compose database)
```

Demo steps 1 to 3 over the API: `POST /ingest {"week_ending": "2026-03-14"}`, `GET /queue`, `GET /cases/{id}`, `GET /passages/{citation_key}`, `POST /cases/{id}/decide {"action": "return", "actor": "...", "message": "..."}`, `GET /cases/{id}/audit`.

## Layout

| Path | Purpose |
| --- | --- |
| `docs/requirements/` | Project brief, domain model, customer workflow, demo script |
| `docs/architecture/` | C4 views (context, containers, backend components), LangGraph state machine, checkpoint sequence |
| `docs/decisions/` | Architecture decision records (MADR style) |
| `docs/planning/` | Initial plan (frozen) and current plan |
| `docs/progress/` | Current state handoff and per-iteration logs |
| `docs/evidence/` | Evidence profile, assumptions, sources, data methodology |
| `backend/` | Python 3.12, FastAPI, LangGraph, rule engine, retrieval, LLM adapter |
| `frontend/` | React, TypeScript, Vite (Iteration 4) |
| `corpus/` | Synthetic agreement and deal memos |
| `data/` | Rule parameters and generated timecards |
| `evals/` | Evaluation cases and gate |
| `deployment/` | Docker compose (database and API) |
| `observability/` | Tracing configuration (Iteration 6) |

## Working rules

See `AGENTS.md`. In short: the author commits by hand, no AI attribution anywhere, no real brands, English only, synthetic data only, and the LLM is the engine for explanation, proposal and drafting with no deterministic fallback.
