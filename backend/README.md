# Backend

Python 3.12 project managed with uv (ADR-015). Iteration 1 added the rule parameter loader, the agreement renderer, the deal memo loader, the seeded timecard generator and the evaluation manifest builder. Iteration 2 added the rule engine (MEAL_PERIOD), the code-owned action policy, PostgreSQL persistence and migrations, corpus ingestion with local embeddings and hybrid retrieval, the LLM adapter v1 (OpenAI-compatible, default gpt-oss-20b on GroqCloud; Anthropic optional), the LangGraph state machine with the human checkpoint, and the FastAPI API.

Configuration comes from the single root `.env` (copy `.env.example`). Commands (run from this folder):

```
uv sync                      # create the virtual environment from uv.lock
uv run pytest                # tests (integration tests need the compose database)
uv run ruff check .          # lint
uv run ptc render-agreement  # render corpus/cgma-2026.1.md from the template and the YAML
uv run ptc generate-data     # write data/generated/ from data/scenarios.yaml (seeded)
uv run ptc build-manifest    # write evals/cases/manifest.yaml
uv run ptc check             # verify that committed outputs equal regenerated outputs

uv run ptc migrate           # apply SQL migrations and create the LangGraph checkpoint tables
uv run ptc seed [--reset]    # load generated timecards and deal memos (reset clears cases and checkpoints)
uv run ptc ingest-corpus     # chunk, embed (local model, downloaded once) and index the corpus
uv run ptc smoke-llm         # one minimal real call through the configured adapter
uv run ptc showcase [--scenario SC-03] [--decision return|approve|escalate] [--message ...]
                             # one scenario end to end with the real LLM, pause, resume, execute, audit
uv run ptc serve             # API on http://127.0.0.1:8000 (docs at /docs)
```

Database: `docker compose -f ../deployment/docker-compose.yml up db` from this folder (or from the repository root without `../`).

Package layout (`src/payroll_triage/`): `params.py` and `calc.py` (single source of numbers and arithmetic), `timecards.py`, `policy.py`, `engine/`, `retrieval/`, `llm/v1/`, `graph/`, `db/`, `api/`, `runtime.py`, `cli.py`. Test doubles (fake adapter, in-memory store) live only under `tests/support/`.
