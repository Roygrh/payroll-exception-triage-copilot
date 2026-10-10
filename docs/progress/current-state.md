# Current state

## Handoff

**Done**
- Iteration 000 (2026-10-07): bootstrap. Rules, tool guardrails (git guard hook), five validator subagents, requirements, architecture, ADR-001 to ADR-014, plan, evidence set.
- Iteration 001 (2026-10-07 to 2026-10-08): domain and data. Rule parameters YAML with schema, rendered agreement, six deal memos, seeded generator (22 timecards), expectation oracle and manifest (18 cases), ADR-015.
- Iteration 002 (2026-10-08): vertical slice MEAL_PERIOD end to end. Shared timecard model and code-owned policy; rule engine tested against the manifest; PostgreSQL 16 with pgvector, migrations, audit triggers and LangGraph checkpoint tables; corpus ingestion with local embeddings and hybrid retrieval (ADR-017); LLM adapter v1 with the OpenAI-compatible default (ADR-016); LangGraph state machine with citation, number and policy validation, durable human checkpoint, execute and audit; FastAPI API for demo steps 1 to 3; C4 level 3 and sequence diagrams. 175 backend tests, 86 hook cases, validators PASS at the gate (see `iterations/iteration-002.md`). OD-06, OD-07, OD-08 closed.
- Iteration 2 status: built; the real-LLM acceptance of P1.I2.S5 moved to Iteration 2b. First real run by the author on 2026-10-08 (gpt-oss-20b on GroqCloud): smoke succeeded (live limits 1,000 requests per day, 8,000 tokens per minute); SC-03 showcase worked end to end but ended in `needs_human_review` (the model wrote "0.5" hours, rejected by the stray-number check); it also revealed the draft-versus-decision gap, bracketed pseudo-references, a wrong `case_status_before` in the audit entry and about 10,000 tokens per case (recorded in `iterations/iteration-002.md`, "Showcase run").
- Last steps (2026-10-09, documentation only): Iteration 2b added to the plan; Phase 1 execution order set to 2b, 4, 3, 5, 6; ADR-016 consequences updated; ADR-018 proposed; `docs/planning/roadmap.md` created.

**Next**
- Iteration **2b**, starting with **P1.I2b.S1** (`hours_late` as an engine fact; prompts forbid unit conversion and any number not given). Needs: the manifest regenerated with the new fact (`ptc build-manifest`, `ptc check`), then S2 to S7 in order. Before S3, run hitl-workflow-validator PRE on the ADR-018 design. Acceptance (S6) needs the free key, the compose database up, `ptc migrate`, `ptc seed`, `ptc ingest-corpus`. Validators per step in `current-plan.md`.
- After 2b: Iteration 4 (UI), then 3, 5, 6 (see `docs/planning/roadmap.md`).

**Open decisions**
- OD-01: Queue priority weights (implemented as proposed in the YAML `queue` block). Owner: author. Confirm or change the YAML; no ADR needed unless the formula changes.
- OD-02: Tier 2 thresholds and judge model (ADR-003). Owner: author. Decide in P1.I3.S3 after the baseline run.
- OD-04: LangGraph instrumentation library for OpenTelemetry (ADR-004). Owner: author. Decide in P1.I6.S1.
- OD-09: partially closed on 2026-10-08 (valid key, smoke call, live limits recorded in ADR-016). Open: the real-LLM acceptance run, now P1.I2b.S6. Owner: author.
- ADR-018 (Proposed): draft after the human decision, merged explain and propose, limited passages. Owner: author. Accept when P1.I2b.S3 and S4 are done (status set in P1.I2b.S7).
- OD-10: Approver authentication (Phase 2; `actor` is self-asserted in Phase 1). Owner: author. ADR in Phase 2.
- Closed in Iteration 2: OD-06, OD-07, OD-08.

## Phase and iteration

Phase 1. Iteration 2 built; its real-LLM acceptance is carried by Iteration 2b (next). Execution order from 2026-10-09: 2b, 4 (UI), 3 (evaluations), 5 (remaining rules), 6 (one command, tracing, rehearsal); iteration numbers are unchanged. Demo strategy: a recorded video and a live online session; the repository remains runnable with a free provider key; demo-visible work comes first because the selection window may be short.

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

- Real-LLM acceptance not yet met: the first real run (2026-10-08) ended SC-03 in `needs_human_review` on a stray "0.5" (P1.I2b.S1, S6).
- The draft is written for the proposed action before the human decides; if the human chooses another action, the message for the proposal is sent unchanged (ADR-018, P1.I2b.S3). Until fixed, run the showcase with the decision equal to the policy action.
- Bracketed pseudo-references such as "[MEAL_PERIOD facts: ...]" pass validation (P1.I2b.S2).
- The decision audit entry records `case_status_before` as the status after the decision instead of the status at the checkpoint (P1.I2b.S5).
- About 10,000 tokens per case, above the 8,000 tokens-per-minute budget (P1.I2b.S4).
- Only MEAL_PERIOD is wired in the engine (`engine/rules.py`); the oracle and the manifest already cover all six rules (Iteration 5).
- No evaluation harness or gate (Iteration 3), no UI (Iteration 4), no tracing (Iteration 6); the API container in compose is defined but the one-command start with seed is Iteration 6.
- The Anthropic adapter is untested (optional provider).
- No authentication: the approver's identity is the `actor` field of the decision request.

## Risks

- Free-tier token budget: live limits are 1,000 requests per day and 8,000 tokens per minute; the first run measured about 10,000 tokens per case. Iteration 2b targets at most 5,000 per MEAL_PERIOD case (ADR-018); if the target is missed, evaluation runs in Iteration 3 take longer and fewer full runs fit in a day. The daily token limit is not reported in the headers.
- Model quality: a 20-billion-parameter open model must keep every number verbatim and cite only given keys; the stray-number and citation validators route failures to human review, so the gate in Iteration 3 may show a lower pass rate than a larger model would. Switching models is configuration (ADR-016) but re-baselines the gate.
- Schedule: five iterations remain (2b, 4, 3, 5, 6) and the selection window may be short; the order puts a recordable UI demo first.
