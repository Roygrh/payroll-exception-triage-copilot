# Current state

## Handoff

**Done**
- Iteration 000 (2026-10-07): bootstrap. Rules, tool guardrails (git guard hook), five validator subagents, requirements, architecture, ADR-001 to ADR-014, plan, evidence set.
- Iteration 001 (2026-10-07 to 2026-10-08): domain and data. Rule parameters YAML with schema, rendered agreement, six deal memos, seeded generator (22 timecards), expectation oracle and manifest (18 cases), ADR-015.
- Iteration 002 (2026-10-08): vertical slice MEAL_PERIOD end to end (engine, PostgreSQL and pgvector, hybrid retrieval, LLM adapter v1, LangGraph graph with the human checkpoint, API).
- Iteration 002b (2026-10-10 to 2026-10-14, closed): fixes from the first real run and token efficiency. Draft after the human decision with a second checkpoint (ADR-018), merged explain and propose, limited passages, HH:MM times and the unit and clock-time meaning check (S8). Author's real runs: SC-03 approve 2,317 tokens per case, SC-05 return 4,741 (`iterations/iteration-002b.md`).
- Iteration 004 (2026-10-21 to 2026-10-22): approver UI (`iterations/iteration-004.md`):
  - **S1:** `frontend/` with React, TypeScript, Vite, Tailwind CSS, Vitest and React Testing Library, exact pins (ADR-020), dev proxy `/api` to the API.
  - **S2:** queue in the API's priority order, counters, "Ingest week" with progress.
  - **S3:** case detail with HH:MM events, fact tiles with units, LLM-marked explanation and proposal, citation buttons opening the full passage, passages retrieved (sent to model or ranked only), model call; the review state shows facts and the reason only (ADR-021).
  - **S4:** Approve, Return and Escalate with progress and a single request per decision; the message confirmation screen (editable body, empty when the draft needs review, cancel); the executed banner, the checkpoint ids before and after, and the audit trail with the sent message next to the original draft.
  - **API (additive, read-only):** `GET /context`; optional queue fields (employee id, occupation, rule titles); optional case-detail fields (finding days as HH:MM, fact units, rule titles, occupation title).
  - **Validators:** test-engineer PASS, code-reviewer and hitl-workflow-validator FAIL then fixed (results in the log). Frontend 35 tests, backend 219 passed and 7 skipped (no database in the session).

**Next**
- **Author walk-through of the UI with real data** (steps below, "See the UI with real data"): SC-05 Return and SC-03 Approve, recording tokens per case and the draft wait in `iteration-004.md`. Then **Iteration 3 (evaluations), starting with P1.I3.S1**; then 5 and 6 (`docs/planning/roadmap.md`).

**Open decisions**
- OD-01: queue priority weights (implemented as proposed in the YAML `queue` block). Owner: author. Confirm or change the YAML; no ADR unless the formula changes.
- OD-02: tier 2 thresholds and judge model (ADR-003). Owner: author. Decide in P1.I3.S3 after the baseline run.
- OD-04: LangGraph instrumentation library for OpenTelemetry (ADR-004). Owner: author. Decide in P1.I6.S1.
- OD-10: approver authentication (Phase 2; `actor` is self-asserted in Phase 1, the UI uses the catalog's demo approver). Owner: author. ADR in Phase 2.
- OD-11 (new, Iteration 4): the draft subject is validated and shown read-only but not carried to execution. Carry it (editable in the UI, stored with the message) or drop it from `DraftOutput` to save tokens. Owner: author. ADR-018 amendment if carried.
- Closed: OD-09 (2026-10-14); OD-06, OD-07, OD-08 (Iteration 2); ADR-018 accepted on 2026-10-10.

## Phase and iteration

Phase 1. Iteration 4 (UI) is built and validated with mocked API data and the fake adapter; demo steps 1 to 3 can be performed in the browser. The author's walk-through with the real model is pending. Execution order from 2026-10-09: 2b (closed), 4 (built), 3 (evaluations), 5 (remaining rules), 6 (one command, tracing, rehearsal). Demo strategy: a recorded video and a live online session. The repository stays runnable with a free provider key.

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
uv run pytest                    # 226 tests; the 7 integration tests use the compose database (ptc_test)
uv run ruff check .
uv run ptc check                 # committed agreement, generated data and manifest equal regeneration
uv run ptc migrate               # tables, audit triggers, LangGraph checkpoint tables
uv run ptc seed [--reset]        # 22 timecards, 10 deal memos; reset erases cases, audit and checkpoints
uv run ptc ingest-corpus         # 106 chunks; downloads the embedding model once (about 67 MB)
uv run ptc smoke-llm             # one real structured call; prints the rate-limit headers
uv run ptc showcase --scenario SC-03 --decision approve [--dry-run]
uv run ptc showcase --scenario SC-05 --decision return [--message ...] [--dry-run]
uv run ptc confirm-message --case CASE-... [--actor ...] (--accept-draft | --message ... | --cancel)
uv run ptc serve                 # API on http://127.0.0.1:8000/docs
uv run ptc render-agreement | generate-data | build-manifest
```

From `frontend/` (Node 24.11.0 or later, ADR-020):

```
npm install                      # once; exact pins from package-lock.json
npm run dev                      # UI on http://localhost:5173, /api proxied to http://127.0.0.1:8000
npm run build                    # type check and static build in dist/
npm test                         # 35 component tests, API mocked
npm run lint
```

API (demo steps 1 to 3; no path prefix):
- `GET /context` (header data, recipients, message limit)
- `POST /ingest {"week_ending": "2026-03-14"}`
- `GET /queue`
- `GET /cases/{id}`: also `finding_days` (HH:MM), `fact_units`, `rule_titles`, `occupation_title`
- `GET /passages/{citation_key}`
- `POST /cases/{id}/decide {"action", "actor"}`: approve executes; return and escalate draft the message and wait at the message step.
- `POST /cases/{id}/message {"actor", "message", "recipient_role"?}` or `{"actor", "cancel": true}`
- `GET /cases/{id}/audit`

## See the UI with real data

1. From the repository root: `docker compose -f deployment/docker-compose.yml up -d db` (the root `.env` holds the provider key).
2. From `backend/`: `uv sync`, then `uv run ptc migrate`.
3. `uv run ptc seed --reset` (erases earlier cases, audit entries and checkpoints, so the demo week can be ingested fresh).
4. `uv run ptc ingest-corpus` if the corpus was not ingested before (downloads the embedding model once; no LLM call).
5. `uv run ptc serve` and leave it running.
6. In a second terminal, from `frontend/`: `npm install` (first time only), then `npm run dev`.
7. Open `http://localhost:5173`. The header shows the week ending 2026-03-14, the payroll cut-off, agreement CGMA 2026.1 and `sam.verhoeven`.
8. Press **Ingest week**. **LLM:** one explain-and-propose call per timecard with a finding (two in the demo week: SC-05 and SC-03); clean timecards make no call. The queue fills with two cases.
9. **SC-05 (Return):** open the top case (Jordan Okafor). Check the events (Meal in 12:24) and the tile "24 min, minimum 30 min". Click `CGMA-2026.1-8.2` and `DM-02` and read the passages. Press **Return**. **LLM:** one draft call (seconds to tens of seconds). On "Confirm the message", edit the body and press **Confirm and return** (no LLM call). The audit screen shows "Timecard returned to Jordan Okafor", status Rejected, the checkpoint ids, the sent text next to the original draft and the entries suggestion, validation, decision, suggestion, decision, execution.
10. **SC-03 (Approve):** back to the queue, open Avery Lindqvist's case and press **Approve** (no LLM call). The audit screen shows the approval, the timecard status Ready for approver 2 and the premium line.
11. Record the tokens per case from the "Model call" cards in `iteration-004.md`, "Author walk-through".

## Known gaps

- The meaning check does not cover number words ("thirty minutes") or which fact a number describes; a correction that asks to change accurate times passes the code checks. Both are carried to the Iteration 3 tier 2 rubric.
- The draft subject is shown read-only and not carried to execution (OD-11).
- The checkpoint ids before and after are kept in the browser tab's session storage (the API returns them only on decide and message); another tab shows none.
- The UI was not reviewed in a real browser by an agent in Iteration 4; the author's walk-through covers layout and contrast on screen.
- The 7 database integration tests were skipped in the Iteration 4 session (no database running); they do not touch the changed code.
- Only MEAL_PERIOD is wired in the engine (`engine/rules.py`); the oracle and the manifest already cover all six rules (Iteration 5).
- No evaluation harness or gate (Iteration 3), no tracing (Iteration 6). Compose has no frontend service yet; the one-command start is Iteration 6.
- A retry of the same decision after a lost checkpoint is audited as `duplicate_attempt` next to the single `executed` entry.
- The Anthropic adapter is untested (optional provider).
- No authentication: the approver's identity is the `actor` field of the request.

## Risks

- **Free-tier token budget:** the live limits are 1,000 requests per day and 8,000 tokens per minute. The SC-05 return used 4,741 tokens per case on the S8 code. Ingesting the week makes two calls back to back; the adapter paces and retries.
- **Draft wait in the browser:** a return or escalate waits for one LLM call; the dev proxy allows two minutes (A-28). A timeout shows an error, and repeating the same decision resumes the same run.
- **Model quality:** failures route to human review, so the Iteration 3 gate may show review cases that need prompt tuning. Switching models is configuration (ADR-016) but re-baselines the gate.
- **Schedule:** three iterations remain (3, 5, 6), and the selection window may be short.
