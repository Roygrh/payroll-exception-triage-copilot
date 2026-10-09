# Current state

## Handoff

**Done**
- Iteration 000 (2026-10-07): bootstrap. Rules, tool guardrails (git guard hook), five validator subagents, requirements, architecture, ADR-001 to ADR-014, plan, evidence set.
- Iteration 001 (2026-10-07 to 2026-10-08): domain and data. Rule parameters YAML with schema, rendered agreement, six deal memos, seeded generator (22 timecards), expectation oracle and manifest (18 cases), ADR-015.
- Iteration 002 (2026-10-08): vertical slice MEAL_PERIOD end to end. Shared timecard model and code-owned policy; rule engine tested against the manifest; PostgreSQL 16 with pgvector, migrations, audit triggers and LangGraph checkpoint tables; corpus ingestion with local embeddings and hybrid retrieval (ADR-017); LLM adapter v1 with the OpenAI-compatible default (ADR-016); LangGraph state machine with citation, number and policy validation, durable human checkpoint, execute and audit; FastAPI API for demo steps 1 to 3; C4 level 3 and sequence diagrams. 175 backend tests, 86 hook cases, validators PASS at the gate (see `iterations/iteration-002.md`). OD-06, OD-07, OD-08 closed.
- Last steps: P1.I2.S7 (API) and P1.I2.S8 (this handoff). The real-LLM acceptance run is pending on a valid provider key (OD-09).

**Next**
- The author: paste a valid `GROQ_API_KEY` into the root `.env`, then from `backend/`: `uv run ptc smoke-llm` (records the live rate-limit headers) and `uv run ptc showcase --decision return` (SC-03 end to end with the real model). Paste the output into `iteration-002.md` under "Showcase run" and the limits into ADR-016. Review and commit Iteration 2.
- Then step **P1.I3.S1** (evaluation harness running the graph on each manifest case with the real adapter; per-case report). Needs: the valid key, the compose database up, `ptc migrate`, `ptc seed`, `ptc ingest-corpus`. Validators: test-engineer, code-reviewer. Note for the harness: load the committed manifest (`load_manifest()`), do not rebuild it; only MEAL_PERIOD cases and clean weeks run until Iteration 5 wires the other rules.

**Open decisions**
- OD-01: Queue priority weights (implemented as proposed in the YAML `queue` block). Owner: author. Confirm or change the YAML; no ADR needed unless the formula changes.
- OD-02: Tier 2 thresholds and judge model (ADR-003). Owner: author. Decide in P1.I3.S3 after the baseline run.
- OD-04: LangGraph instrumentation library for OpenTelemetry (ADR-004). Owner: author. Decide in P1.I6.S1.
- OD-09: Provide a valid provider key and record the showcase output and the live rate limits. Owner: author. Updates `iteration-002.md` and ADR-016.
- OD-10: Approver authentication (Phase 2; `actor` is self-asserted in Phase 1). Owner: author. ADR in Phase 2.
- Closed in Iteration 2: OD-06, OD-07, OD-08.

## Phase and iteration

Phase 1. Iteration 2 complete except the real-LLM acceptance run (OD-09). Iteration 3 (evaluation harness and two-tier gate) not started.

## What runs today

From the repository root:

```
cp .env.example .env                                  # then paste the provider key
docker compose -f deployment/docker-compose.yml up -d db
bash .claude/hooks/tests/run.sh                       # 86 git guard cases
```

From `backend/` (uv required, ADR-015):

```
uv sync
uv run pytest                    # 175 tests; the 7 integration tests use the compose database (ptc_test)
uv run ruff check .
uv run ptc check                 # committed agreement, generated data and manifest equal regeneration
uv run ptc migrate               # tables, audit triggers, LangGraph checkpoint tables
uv run ptc seed [--reset]        # 22 timecards, 10 deal memos; reset erases cases, audit and checkpoints
uv run ptc ingest-corpus         # 106 chunks; downloads the embedding model once (about 67 MB)
uv run ptc smoke-llm             # one real structured call; prints the rate-limit headers
uv run ptc showcase --decision return [--scenario SC-03] [--message ...]
uv run ptc serve                 # API on http://127.0.0.1:8000/docs
uv run ptc render-agreement | generate-data | build-manifest
```

API (demo steps 1 to 3): `POST /ingest {"week_ending": "2026-03-14"}`, `GET /queue`, `GET /cases/{id}` (includes `output_status` per LLM output and the checkpoint id), `GET /passages/{citation_key}`, `POST /cases/{id}/decide {"action", "actor", "message"}`, `GET /cases/{id}/audit`.

## Known gaps

- Real-LLM acceptance run not yet performed (invalid key); the provider path is exercised up to the 401 and routes to `needs_human_review`.
- Only MEAL_PERIOD is wired in the engine (`engine/rules.py`); the oracle and the manifest already cover all six rules (Iteration 5).
- No evaluation harness or gate (Iteration 3), no UI (Iteration 4), no tracing (Iteration 6); the API container in compose is defined but the one-command start with seed is Iteration 6.
- The Anthropic adapter is untested (optional provider).
- No authentication: the approver's identity is the `actor` field of the decision request.

## Risks

- Free-tier token budget: three structured calls per case at low reasoning effort; a full week ingest is paced at 30 requests per minute. The Iteration 3 harness over 18 cases (54 calls plus the judge) must respect the daily limits; batch runs may need to spread over time.
- Model quality: a 20-billion-parameter open model must keep every number verbatim and cite only given keys; the stray-number and citation validators route failures to human review, so the gate in Iteration 3 may show a lower pass rate than a larger model would. Switching models is configuration (ADR-016) but re-baselines the gate.
- Schedule: four iterations remain for the two-week target.
