# Current state

## Handoff

**Done**
- Iteration 000 (2026-10-07): bootstrap. Rules, tool guardrails (git guard hook), five validator subagents, requirements, architecture, ADR-001 to ADR-014, plan, evidence set.
- Iteration 001 (2026-10-07 to 2026-10-08): domain and data. Rule parameters YAML with schema, rendered agreement, six deal memos, seeded generator (22 timecards), expectation oracle and manifest (18 cases), ADR-015.
- Iteration 002 (2026-10-08): vertical slice MEAL_PERIOD end to end (engine, PostgreSQL and pgvector, hybrid retrieval, LLM adapter v1, LangGraph graph with the human checkpoint, API). First real run by the author on 2026-10-08: SC-03 ended in `needs_human_review` (stray "0.5"), plus a draft-versus-decision gap, pseudo-references, a wrong audit field and about 10,000 tokens per case (`iterations/iteration-002.md`).
- Iteration 002b (2026-10-10), steps S1 to S5 and S7, all validated (`iterations/iteration-002b.md`):
  - **S1:** `hours_late` is an engine fact (facts schema version 2, manifest regenerated) and the prompts forbid unit conversion.
  - **S2:** pseudo-references are rejected, and so are citation keys written without brackets that were not sent or are malformed.
  - **S3:** the message is drafted after the human chooses return or escalate, for that action, and the human confirms or edits it at a second checkpoint (`POST /cases/{id}/message`, `ptc confirm-message`). A draft failure marks the case `needs_human_review` and the human writes the message. Execution is idempotent and audited in one transaction.
  - **S4:** explain and propose are one call; only the finding's sections and the deal memo are sent; prompts are compact. Offline estimate: SC-03 9,613 to 1,993 input tokens per case, SC-05 10,071 to 3,910. The showcase prints tokens per case, and `--dry-run` estimates them offline (ADR-019, tiktoken).
  - **S5:** `case_status_before` comes from the checkpoint.
  - **Totals:** 210 tests, 86 hook cases.
  - **Decisions:** ADR-018 Accepted; ADR-019 Accepted.

**Next**
- **P1.I2b.S6**, the acceptance run with the real LLM, by the author. Exact commands and pass criteria are in `iterations/iteration-002b.md`, "S6: acceptance run (author)". It needs the free key in the root `.env`, the compose database up, `uv sync` (tiktoken), `uv run ptc migrate`, and `uv run ptc seed --reset` (no corpus re-ingest needed). Then run:
  - `ptc showcase --decision approve` on SC-03;
  - `ptc showcase --scenario SC-05 --decision return`;
  - `ptc confirm-message --case CASE-EMP-1002-20260314 --accept-draft`.

  Record the `TOKENS PER CASE` lines (target at most 5,000 each) and the outputs in `iteration-002b.md`. Then run the grounding-evaluator on the outputs and the hitl-workflow-validator GATE.
- After S6: Iteration 4 (UI) on the two-step decision flow (decide, then confirm the message), then 3, 5, 6 (`docs/planning/roadmap.md`).

**Open decisions**
- OD-09: real-LLM acceptance run, now P1.I2b.S6 (the smoke call and the live limits were done on 2026-10-08). Owner: author. No ADR expected; results go in `iteration-002b.md`. If the tokens per case exceed 5,000, decide on a further cut (owner: author) and record it as an ADR-018 consequence.
- OD-01: queue priority weights (implemented as proposed in the YAML `queue` block). Owner: author. Confirm or change the YAML; no ADR unless the formula changes.
- OD-02: tier 2 thresholds and judge model (ADR-003). Owner: author. Decide in P1.I3.S3 after the baseline run.
- OD-04: LangGraph instrumentation library for OpenTelemetry (ADR-004). Owner: author. Decide in P1.I6.S1.
- OD-10: approver authentication (Phase 2; `actor` is self-asserted in Phase 1). Owner: author. ADR in Phase 2.
- Closed: OD-06, OD-07, OD-08 (Iteration 2); ADR-018 accepted on 2026-10-10.

## Phase and iteration

Phase 1. Iteration 2b is built and validated; its real-LLM acceptance (S6) is the author's next step. Execution order from 2026-10-09: 2b, 4 (UI), 3 (evaluations), 5 (remaining rules), 6 (one command, tracing, rehearsal); iteration numbers are unchanged. Demo strategy: a recorded video and a live online session; the repository stays runnable with a free provider key.

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
uv run pytest                    # 210 tests; the 7 integration tests use the compose database (ptc_test)
uv run ruff check .
uv run ptc check                 # committed agreement, generated data and manifest equal regeneration
uv run ptc migrate               # tables, audit triggers, LangGraph checkpoint tables
uv run ptc seed [--reset]        # 22 timecards, 10 deal memos; reset erases cases, audit and checkpoints
uv run ptc ingest-corpus         # 106 chunks; downloads the embedding model once (about 67 MB)
uv run ptc smoke-llm             # one real structured call; prints the rate-limit headers
uv run ptc showcase --scenario SC-03 --decision approve [--dry-run]
uv run ptc showcase --scenario SC-05 --decision return [--message ...] [--dry-run]
                                 # return and escalate stop at the message step after printing the draft
uv run ptc confirm-message --case CASE-... [--actor ...] (--accept-draft | --message ... | --cancel)
uv run ptc serve                 # API on http://127.0.0.1:8000/docs
uv run ptc render-agreement | generate-data | build-manifest
```

`--dry-run` makes no provider call and needs no database or key; it prints estimated input tokens per call and per case (ADR-019). The real showcase prints `TOKENS PER CASE` from the provider's usage.

API (demo steps 1 to 3):
- `POST /ingest {"week_ending": "2026-03-14"}`
- `GET /queue`
- `GET /cases/{id}`: includes `output_status` per LLM output, `chosen_action`, `waiting_on`, the checkpoint id, and the chunks with `sent_to_model`.
- `GET /passages/{citation_key}`
- `POST /cases/{id}/decide {"action", "actor"}`: approve executes; return and escalate draft the message and wait at the message step.
- `POST /cases/{id}/message {"actor", "message", "recipient_role"?}` or `{"actor", "cancel": true}`
- `GET /cases/{id}/audit`

## Known gaps

- The real-LLM acceptance is not yet run on the 2b code (S6). The token reduction is an offline estimate until then. Output and reasoning tokens are known only from the provider.
- Only MEAL_PERIOD is wired in the engine (`engine/rules.py`); the oracle and the manifest already cover all six rules (Iteration 5).
- No evaluation harness or gate (Iteration 3), no UI (Iteration 4), no tracing (Iteration 6). The API container is defined in compose, but the one-command start with seed is Iteration 6.
- The draft subject is validated but not carried to execution (decide in Iteration 4).
- A retry of the same decision after a lost checkpoint is audited as `duplicate_attempt` next to the single `executed` entry.
- The Anthropic adapter is untested (optional provider).
- No authentication: the approver's identity is the `actor` field of the request.

## Risks

- **Free-tier token budget:** the live limits are 1,000 requests per day and 8,000 tokens per minute. The 2b estimate is about 2,000 input tokens for an approve case and 3,900 for a return case, plus output. If the model's outputs are long, a return case may exceed 5,000 in total; S6 measures it.
- **Model quality:** a 20-billion-parameter open model must keep every number verbatim and cite only the given keys, now with stricter checks (unbracketed keys, the draft citing the governing section). Failures route to human review, so the S6 run or the Iteration 3 gate may show review cases that need prompt tuning. Switching models is configuration (ADR-016) but re-baselines the gate.
- **Two-step decision in the UI:** the decide request for return and escalate waits for one LLM call (seconds to tens of seconds on the free tier). Iteration 4 must show progress and handle a repeated request, which the service already supports.
- **Schedule:** four iterations remain after 2b (4, 3, 5, 6), and the selection window may be short.
