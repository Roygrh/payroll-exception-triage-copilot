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
- Iteration 002b (2026-10-14), S6 and S8 (`iterations/iteration-002b.md`):
  - **S6 (author, real LLM):** passed. SC-03 approve in one call, 2,317 tokens per case; SC-05 return in two calls, 4,732 tokens per case; the message confirmation made no LLM call. Both are within the 5,000 target. The offline estimate held within about 1 percent of the input tokens reported by the provider (A-27 confirmed).
  - **S8:** the same run showed a meaning error that the checks of that time passed: "the meal out at 12.0 minutes after Call", where 12.0 was the clock time of meal out. Prompts now show timecard times as HH:MM times of day, and each fact declares its unit. Validation now rejects three things: a number written with minutes or hours that matches no fact or sent passage of that unit, an HH:MM time that is not an event of the case, and a clock time written as a duration. A clock time also no longer makes a bare number count as present. Validators: test-engineer PASS, code-reviewer FAIL then PASS, grounding-evaluator PASS, hitl-workflow-validator GATE PASS. 217 tests pass with the database tests excluded (7 more need the database). Offline estimate after S8: SC-03 2,029 input tokens per case, SC-05 3,982.

**Next**
- **The author re-runs SC-05 on the S8 code** (exact commands and pass criteria in `iterations/iteration-002b.md`, "S8: re-run of SC-05 (author)"). It needs the compose database up, `uv run ptc seed --reset`, then `ptc showcase --scenario SC-05 --decision return` and `ptc confirm-message --case CASE-EMP-1002-20260314 --accept-draft`. If it passes, Iteration 2b is done.
- Then **Iteration 4 (UI)** on the two-step decision flow (decide, then confirm the message), then 3, 5, 6 (`docs/planning/roadmap.md`). The UI should show timecard times as HH:MM, as the prompts now do.

**Open decisions**
- OD-01: queue priority weights (implemented as proposed in the YAML `queue` block). Owner: author. Confirm or change the YAML; no ADR unless the formula changes.
- OD-02: tier 2 thresholds and judge model (ADR-003). Owner: author. Decide in P1.I3.S3 after the baseline run.
- OD-04: LangGraph instrumentation library for OpenTelemetry (ADR-004). Owner: author. Decide in P1.I6.S1.
- OD-10: approver authentication (Phase 2; `actor` is self-asserted in Phase 1). Owner: author. ADR in Phase 2.
- Closed: OD-09 (the real-LLM acceptance, P1.I2b.S6, passed on 2026-10-14); OD-06, OD-07, OD-08 (Iteration 2); ADR-018 accepted on 2026-10-10.

## Phase and iteration

Phase 1, Iteration 2b. S1 to S8 are done and validated. S6 passed in the author's run of 2026-10-14. S8, the fix for the meaning error found in that run, is validated offline. The iteration closes after the author re-runs SC-05 on the S8 code. Execution order from 2026-10-09: 2b, 4 (UI), 3 (evaluations), 5 (remaining rules), 6 (one command, tracing, rehearsal). Iteration numbers are unchanged. Demo strategy: a recorded video and a live online session. The repository stays runnable with a free provider key.

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
uv run pytest                    # 224 tests; the 7 integration tests use the compose database (ptc_test)
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

- The S8 code is validated with the fake adapter only. The real model has not yet run on it; that is the author's SC-05 re-run.
- The meaning check covers numbers written with minutes or hours (also min, mins, hr, hrs) and HH:MM times. It does not cover number words ("thirty minutes", "half an hour"). It also does not check which fact a number describes: "the meal lasted 6.0 hours" passes on SC-05 because 6.0 hours is the deadline. Both are carried to the Iteration 3 tier 2 rubric.
- The 7 database integration tests were not re-run in the S8 session, to avoid database writes. They do not touch the changed code.
- Only MEAL_PERIOD is wired in the engine (`engine/rules.py`); the oracle and the manifest already cover all six rules (Iteration 5).
- No evaluation harness or gate (Iteration 3), no UI (Iteration 4), no tracing (Iteration 6). The API container is defined in compose, but the one-command start with seed is Iteration 6.
- The draft subject is validated but not carried to execution (decide in Iteration 4).
- A retry of the same decision after a lost checkpoint is audited as `duplicate_attempt` next to the single `executed` entry.
- The Anthropic adapter is untested (optional provider).
- No authentication: the approver's identity is the `actor` field of the request.

## Risks

- **Free-tier token budget:** the live limits are 1,000 requests per day and 8,000 tokens per minute. S6 measured 2,317 tokens per case for SC-03 and 4,732 for SC-05. S8 adds about 70 input tokens to a return case (offline estimate 3,982, was 3,910), so SC-05 should land near 4,800, about 200 under the target. Longer model outputs could push a return case past 5,000.
- **Model quality:** a 20-billion-parameter open model must keep every number verbatim and cite only the given keys, now with stricter checks (unbracketed keys, the draft citing the governing section, units and clock times since S8). The S8 checks are new for the model and are deliberately strict: a time written in a.m./p.m. form, for example, routes to review. Failures route to human review, so the SC-05 re-run or the Iteration 3 gate may show review cases that need prompt tuning. Switching models is configuration (ADR-016) but re-baselines the gate.
- **Two-step decision in the UI:** the decide request for return and escalate waits for one LLM call (seconds to tens of seconds on the free tier). Iteration 4 must show progress and handle a repeated request, which the service already supports.
- **Schedule:** four iterations remain after 2b (4, 3, 5, 6), and the selection window may be short.
