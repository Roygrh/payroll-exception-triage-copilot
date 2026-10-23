# Iteration 004: UI

Dates: 2026-10-21 to 2026-10-22
Status: built and validated with mocked API data and the fake adapter; demo step 3 with the real model is the author's walk-through (see "Author walk-through").
Phase: 1
Scope: Phase 1, Iteration 4 as defined in `docs/planning/current-plan.md` (steps P1.I4.S1 to S5), on the two-step decision flow of ADR-018. No agent made a real LLM call: frontend tests mock the API and backend tests use the fake adapter. No rule logic, prompt, validation, policy, data or graph code changed.

## Summary

The approver works the queue in a browser. Four screens follow the approved design:

- **Queue** (`#/`): counters by suggested action and by status, an "Ingest week" button that disables itself while it runs and shows elapsed time, and the open cases in the API's priority order. Clean timecards never appear.
- **Case detail** (`#/cases/{id}`): the finding day's events as HH:MM, the engine facts as labelled tiles with units ("24 min, minimum 30 min"), the validated explanation and proposal marked "LLM generated" with their validation badge, citation buttons that open the full passage (key, heading, version, text) in a side panel, the ranked passages marked "sent to model" or "ranked only", and the model call (model, input, output and total tokens, latency). In `needs_human_review` a banner gives the reason and only facts are shown (ADR-021). The decision card has Approve, Return and Escalate.
- **Confirm the message** (`#/cases/{id}/message`): a three-step indicator, the recipient, the draft's subject (read-only, see "Deviations"), the editable body, the draft's validity badge and token count, "Cancel" and "Confirm and return" or "Confirm and escalate". A draft that needs review is not shown and the body starts empty.
- **Executed and audit trail** (`#/cases/{id}/audit`): a success banner ("Timecard returned to Jordan Okafor", case status, timecard status, premium line for an approval), the checkpoint ids before and after each resume, and a timeline of every audit entry (id, UTC time, kind, actor, title and detail); the executed decision shows the message sent next to the original draft.

The API gained read-only display data (one new endpoint, optional fields, no field changed or removed). ADR-020 records the frontend tooling and ADR-021 the review-state display rule.

## Author decisions recorded at the start of the iteration

- Stack (ADR-013): React, TypeScript and Vite in `frontend/`; Tailwind CSS; Vitest with React Testing Library; ADR-020 written with exact pins.
- Node 24.11.0 and npm 11.6.2 on the author's machine.
- The Vite dev server proxies `/api` to `http://127.0.0.1:8000`; the API needs no CORS change.
- Inter and JetBrains Mono bundled from npm packages, no CDN.
- The approved four-screen design (header, colors, pills, contrast, keyboard access, 44 px targets, phone width).
- The approver is `sam.verhoeven`, self-asserted (OD-10).
- No real LLM call, no `ptc ingest`, `showcase`, `confirm-message` or `smoke-llm`; no change to rules, prompts, validation, policy, data or graph.

## API inventory before the UI (read on 2026-10-21)

The API has no path prefix. Request and response shapes as returned by `api/app.py` and `graph/service.py`:

| Route | Request | Response |
| --- | --- | --- |
| `GET /health` | none | `{status, settings}` (redacted settings) |
| `POST /ingest` | `{week_ending}` | `{week_ending, results: [{timecard_id, case_id, status, review_reason, checkpoint_id, waiting_on, llm_calls}]}` (clean timecards: `case_id` null, `status: "clean"`) |
| `GET /queue` | none | `{count, cases: [case record + employee_name, department, rule_ids]}`; open cases only, ordered by priority, week ending, id |
| `GET /cases/{id}` | none | `{case, timecard (decimal hours), explanation, proposal, draft (valid only), output_status {explain, propose, draft}, validation, draft_validation, review_reason, chunks [{citation_key, source_type, version, heading, sent_to_model}], chosen_action, decision, execution, cancelled_rounds, llm_calls [{node, provider, model, adapter_version, input_tokens, output_tokens, latency_ms, attempts}], pending_retry, checkpoint_id, waiting_on, suggestions}` |
| `POST /cases/{id}/decide` | `{action, actor}` | `{case_id, status, waiting_on, execution, audit_ids, llm_calls, checkpoint_id_before, checkpoint_id_after, retried_execution}`; at the message step also `chosen_action, draft, draft_status, review_reason` |
| `POST /cases/{id}/message` | `{actor, message, recipient_role?}` or `{actor, cancel: true}` | as decide |
| `GET /cases/{id}/audit` | none | `{case_id, entries: [{id, case_id, entry_kind, actor, payload, created_at}]}` |
| `GET /passages/{key}` | none | `{source_type, citation_key, version, section, heading, body}` |

Gaps found: the timecard events were decimal hours only; the queue had no employee id, occupation or rule title; the header context (week ending, payroll run, agreement version, approver) and the allowed recipients and message limit were not exposed. The passages with `sent_to_model`, the token summary of the LLM calls and the draft validity were already returned.

## API changes (all additive, read-only)

- **New `GET /context`:** `{week_ending, as_of_date, payroll_run_date, agreement {code, name, version}, demo_approver, recipients {return, escalate}, max_message_length}`, from the catalog, the parameters, the clock and `graph/execute.py`.
- **`GET /queue` items, new optional fields:** `employee_id`, `occupation_code`, `occupation_title` (from the deal memo), `rule_titles` (rule id to title, from `data/rule-parameters.yaml`).
- **`GET /cases/{id}`, new optional fields:** `finding_days` (per finding: `rule_id`, `day_date`, `weekday`, `events [{field, time}]` with `time` from `calc.clock_time`, for example "12:24" or "02:30 next day", null when missing), `fact_units` (per rule, from `engine/facts.fact_units`), `rule_titles`, `occupation_title`.
- No existing field changed or was removed; `graph/` is untouched. Tests: `backend/tests/test_api.py::test_ui_read_fields_are_additive`, `::test_finding_days_marks_next_day_and_missing_events`.

## Steps completed

| Step | Artifact | Acceptance evidence | Validators |
| --- | --- | --- | --- |
| P1.I4.S1 | `frontend/` (`package.json` with exact pins, `.npmrc`, `package-lock.json`, `vite.config.ts` with the `/api` proxy, `tsconfig.json`, `eslint.config.js`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/router.ts`, `src/api/client.ts`, `src/api/types.ts`, `src/index.css`, `src/test/`), `frontend/README.md`, ADR-020 | `npm run build`, `npm test`, `npm run lint` pass; builds and runs against the API: the in-memory API (fake adapter) served behind `npm run dev` answered `/api/context`, `/api/ingest`, `/api/queue`, `/api/cases/...`, decide, message and audit through the proxy, and the index page returned 200 | test-engineer PASS |
| P1.I4.S2 | `src/pages/QueuePage.tsx`, `src/format.ts`, `src/components/ui.tsx`, `src/components/Header.tsx`, API queue fields and `/context` | Order equals the API's order, also when it is not sorted by any visible column (`QueuePage.test.tsx`, "keeps the API's priority order"); clean timecards absent after an ingest of 10 timecards with 8 clean ("ingests the week once ..."); one ingest request while running | test-engineer PASS, code-reviewer PASS |
| P1.I4.S3 | `src/pages/CaseDetailPage.tsx`, `src/components/CaseParts.tsx`, API case-detail fields, ADR-021 | Clicking a citation shows the exact passage text, its key, heading and version (`CaseDetailPage.test.tsx`, "opens the exact passage ..."); in `needs_human_review` only facts and the reason are shown, also when every output validated ("shows only the facts ...", "still hides the explanation and proposal ..."); events as HH:MM, never decimal hours | hitl-workflow-validator, code-reviewer PASS (see "Validation") |
| P1.I4.S4 | decision card and retry card in `CaseDetailPage.tsx`, `src/pages/ConfirmMessagePage.tsx`, `src/pages/AuditPage.tsx`, `src/checkpoints.ts` | Approve executes and opens the audit trail; Return and Escalate show progress while the draft is written and send one decision on repeated clicks; the message is editable, a draft that needs review starts empty, cancel returns to the decision, confirm sends once; the audit screen lists suggestion, validation, decision and execution entries, the message sent next to the original draft, and the checkpoint ids before and after each resume (`CaseDetailPage.test.tsx`, `ConfirmMessagePage.test.tsx`, `AuditPage.test.tsx`). Demo step 3 with the real model: author walk-through | hitl-workflow-validator GATE (see "Validation"), test-engineer PASS |
| P1.I4.S5 | this file, `current-state.md`, `roadmap.md`, `current-plan.md` (status line, plan changes entry, Iteration 2b status line corrected), `assumptions.md` (A-28) | Procedure in AGENTS.md section 5 | author |

## Validation

- **test-engineer (POST, S1, S2, S4): PASS.** Frontend 5 files, 25 tests at its run (35 after the fixes below); backend 219 passed, 7 skipped (the database integration tests, no database running), ruff and `ptc check` clean. One minor: the escalate success path was not asserted; fixed (tests added for the escalate progress, its decide body and navigation, and one confirm request).
- **code-reviewer (POST, S2, S3): PASS** with eight minors and four infos. Fixed: the review banner wording, a label pointing at a non-form element, a header focus ring below 3:1, focus not moving on a route change, the draft token count of a cancelled round, missing tests (review gate with valid outputs, repeated confirm, retry card), a test literal for the message limit. Kept as the author's design wording: the column "Suggested action" (it shows the code's policy action) and the header label "Payroll cut-off" (it shows `payroll_run_date`). A validated draft is shown on a review case, as ADR-018 allows; documented in code and in ADR-021, with a test.
- **hitl-workflow-validator (POST S3, GATE S4): FAIL, then fixed** (re-run result below). Major: the audit screen did not show the original draft next to the edited text, nor the checkpoint ids before and after, which demo step 3 requires. Fixed in `AuditPage.tsx` and `checkpoints.ts`. Minors: ADR-009 said a mismatched justification is shown as unvalidated, while the design shows facts only (recorded in ADR-021, ADR-009 annotated); the decision card stayed locked when a decide left the case on the page (fixed, tested). Checks 1 to 6 held: no write path for the LLM, both checkpoints enforced, no deterministic fallback, honest labels and status, no double submission, every audit kind listed.
- **Re-runs after the fixes:** the code-reviewer and the hitl-workflow-validator both found a new major in the first fix round: the audit screen labelled a message the approver wrote, after a draft that failed validation, as "(draft unchanged)". Fixed: the label now comes only from the backend's `message_source`, the draft's badge is tri-state, and a draft that was not shown is marked "Not shown to the approver". Tests cover `draft_confirmed`, `draft_edited`, `human_written` with an invalid draft and `human_written` with no draft. Final verdicts: **code-reviewer PASS** (one info, applied: the note's wording for a draft that was not validated); **hitl-workflow-validator GATE PASS** (checks 1 to 6 hold).

## Deviations from the plan

1. **New read-only endpoint and optional fields** (listed under "API changes"), as the author allowed for API gaps. No graph or service change.
2. **The draft subject is shown read-only.** The design asks for an editable subject, but `POST /cases/{id}/message` carries only the body and execution does not store a subject (known gap since Iteration 2b). Making it editable would mean changing the execute path, which this iteration excludes, and an edited subject that is not sent would mislead the approver. The UI says so ("only the body is sent ... today"). New open decision OD-11.
3. **The checkpoint ids before and after** come from the decide and message responses only, so the UI keeps them per case in the browser tab's session storage. Another tab, a reload in a new session or blocked storage shows no "Graph resumes" card; the audit trail itself is unaffected.
4. **ADR-021 (new)** records the review-state display rule from the approved design and refines ADR-009's reconciliation paragraph.
5. **Two pins below the newest release** (ADR-020): TypeScript 6.0.3 (typescript-eslint supports below 6.1) and jsdom 29.1.1 (jsdom 30 needs Node 24.15).
6. **No browser screenshot review** was made in this session; layout and contrast were reviewed from the code by the code-reviewer and are covered by the author's walk-through.

## Validator findings carried forward

- **OD-11, draft subject:** carry the subject to execution (editable in the UI) or drop it from `DraftOutput` to save tokens. Owner: author.
- **Naming:** "Suggested action" in the queue shows the code's policy action (ADR-009); "Payroll cut-off" in the header shows `payroll_run_date`. Rename if the author prefers "Policy action" and "Payroll run".
- **Fixtures repeat YAML values** (`deadline_hours`, `min_duration_minutes`, `penalty_usd` in `frontend/src/test/fixtures.ts`): they can drift from `data/rule-parameters.yaml` without a failing test. Optional: a backend test that compares the demo-week API responses with the fixture shapes.
- **Draft token count:** taken from the latest `draft` call in `llm_calls`; hidden when the current round has no draft. A round whose call raised before it was recorded is not distinguishable in the API.
- **A stalled resume value at a checkpoint node** (the service's pending-resume path) shows the normal decision or message form; a different submission gets a 409 naming the stored decision (safe, less guided than the retry card).
- **The 7 database integration tests** skipped in this session (no database running); re-run them with the compose database up.
- Carried from Iteration 2b, unchanged: the Iteration 3 tier 2 rubric items, the private LangGraph constant, the untested Anthropic adapter.

## Metrics

| Metric | Value |
| --- | --- |
| Frontend tests | 35 passed in 5 files (`npm test`) |
| Backend tests | 219 passed, 7 skipped (the database integration tests; no database was running), 226 in total; 2 new in `test_api.py` |
| Lint | eslint clean; ruff check and format clean |
| `ptc check` | all committed outputs are current |
| Frontend build | `npm run build` passes (type check, then about 257 kB of JavaScript, 79 kB gzipped, plus bundled font files) |
| Real LLM calls by agents | 0 |
| Hygiene scans | em dashes and AI attribution: none in changed files; brand term list: no hit in source files |

## Author walk-through (to record)

The steps are in `current-state.md`, "See the UI with real data". Record here: tokens per case for SC-03 approve and SC-05 return as shown in the "Model call" card, the time the Return draft took, and any review routing.

## Open decisions raised or still open

- **OD-11 (new):** the draft subject (carry to execution or drop). Owner: author. ADR-018 amendment if carried.
- OD-01, OD-02, OD-04, OD-10: unchanged (see `current-state.md`).
