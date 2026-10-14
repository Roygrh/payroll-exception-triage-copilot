# Iteration 002b: Fixes from the first real run and token efficiency

Dates: 2026-10-10
Phase: 1
Scope: Phase 1, Iteration 2b as defined in `docs/planning/current-plan.md` (steps P1.I2b.S1 to S5 and S7). Step S6 (acceptance with the real LLM) is performed by the author after this session; its commands and pass criteria are under "S6: acceptance run (author)". No real LLM call was made in this session: every test uses the fake adapter and the token measurement is offline (ADR-019).

## Summary

The four problems found in the first real run (`iteration-002.md`, "Showcase run") are fixed in code and covered by tests, and the token cost per case is cut by about 60 to 80 percent on the offline estimate.

- **S1:** the engine computes `hours_late` (facts schema version 2) and the prompts forbid unit conversion and any number not given, so "0.5 hours" is now a fact rather than a stray number.
- **S2:** bracketed text that is not a citation key is rejected. Citation keys written without brackets are validated too.
- **S3:** the message is drafted after the human chooses return or escalate, for the action the human chose, and is confirmed or edited at a second checkpoint before execute (ADR-018). Approve makes no draft call. A draft failure marks the case `needs_human_review`, and the human writes the message.
- **S4:** explain and propose are one call. Only the finding's own sections and the case's deal memo are sent. Inputs are serialized compactly. The showcase prints the provider's tokens per case, and `--dry-run` estimates input tokens offline.
- **S5:** `case_status_before` in the decision audit entry is the status at the checkpoint.

The suite grew from 175 to 210 tests. `ptc check` is green, and the hook suite (86 cases) passes. The hitl-workflow-validator reviewed the design PRE twice before the graph was coded (FAIL, then PASS).

## Author decisions recorded at the start of the iteration

- The 2b log is this file, `docs/progress/iterations/iteration-002b.md`.
- ADR-018 design choices accepted: the approver confirms or edits the drafted message before execute; if the draft call fails, the human writes the message and no template is used.
- `docs/requirements/demo-script.md`, `docs/architecture/overview.md` and `docs/requirements/customer-workflow.md` are updated in S3 to the new draft flow (done).
- ADR-018 is set to Accepted in S7 only if S3 and S4 are done and validated (see S7 below).
- No real LLM calls in this session: no `smoke-llm`, no `showcase` without `--dry-run`. Input tokens are measured offline with a tokenizer suited to the default model, which needed a new dependency and therefore ADR-019. The real counts are recorded by the author in S6.

## Steps completed

| Step | Artifact | Acceptance evidence | Validators |
| --- | --- | --- | --- |
| P1.I2b.S1 | `calc.py` (`MealFacts.hours_late = tenths(minutes_late / 60)`, minutes_late unchanged), `engine/facts.py` (`MealPeriodFacts.hours_late`, `FACTS_SCHEMA_VERSION = 2`), `engine/rules.py`, regenerated `evals/cases/manifest.yaml` (only `hours_late` lines added), `graph/prompts.py` (rule 2: never convert units, copy every number with the unit of its fact, write no other number), `domain-model.md`, tests | Engine facts equal the regenerated manifest (`test_engine.py`, `test_hours_late_equals_minutes_late_for_every_meal_finding`); `ptc check` green; "0.5" is stray without `hours_late` and valid with it (`test_half_hour_is_stray_without_hours_late_and_valid_with_it`); the SC-03 explanation "0.5 hours (30 minutes) late" validates end to end (`test_half_hour_in_the_explanation_validates_on_sc03`) | test-engineer PASS, code-reviewer (see gate), domain-consistency-validator PASS, grounding-evaluator PASS |
| P1.I2b.S2 | `graph/nodes.py` (`pseudo_references`, `cited_keys` reads keys in brackets, in key lists and in prose), prompt rule 3 (square brackets only for citation keys; never a key outside them), tests | "[MEAL_PERIOD facts: hours_late]" routes to needs human review; `[CGMA-2026.1-8.2, DM-01]` passes; unbracketed keys not sent or of another memo are rejected (`test_pseudo_reference_routes_to_review_and_valid_keys_pass`, `test_unbracketed_keys_are_validated_too`) | test-engineer PASS, code-reviewer, grounding-evaluator PASS (its major, unbracketed keys, fixed) |
| P1.I2b.S3 | `graph/build.py`, `nodes.py` (`human_checkpoint`, `draft`, `validate_draft`, `message_checkpoint`), `execute.py` (`validate_choice`, `validate_message`, no default escalation note), `service.py` (`decide`, `confirm_message`, resume validation, retries, per-thread lock), `db/store.py` (`record_llm_output`, guarded and audited `apply_execution`), `api/app.py` (`POST /cases/{id}/decide`, `POST /cases/{id}/message`), `showcase.py`, `cli.py` (`confirm-message`), docs (overview sections 3 to 9, demo-script steps 2 to 4, customer-workflow), ADR-018 implementation design | Approve makes no draft call and executes; return and escalate draft for the chosen action, the human edits and confirms, execute sends the confirmed text (`test_resume_with_edited_message_executes_return_under_human_identity`, `test_return_on_an_approve_case_drafts_for_the_return`); a draft failure marks the case needs human review with no template and the human writes the message (`test_draft_failure_marks_the_case_for_review_and_the_human_writes`); the audit keeps the action, the original draft and the confirmed text; cancel, wrong endpoint, actor checks, stalled checkpoints and lost-checkpoint retries tested | hitl-workflow-validator PRE FAIL then PASS, GATE PASS (re-confirmation below), test-engineer PASS, code-reviewer FAIL then fixed (re-review below) |
| P1.I2b.S4 | `graph/prompts.py` (`ExplainProposeOutput`, `passages_for_model`, compact one-line JSON, passages as plain text, fact meanings once per rule, schema titles removed), merged `explain_propose` node with a doubled output cap, `tokens.py` and `ptc showcase --dry-run` (ADR-019), token totals per case in the showcase, before and after estimates below | Offline estimate: SC-03 approve 9,613 to 1,993 input tokens per case; SC-05 return 10,071 to 3,910. Every validation applies to each part of the merged output (`test_each_check_applies_to_the_proposal_part`, explanation tests); the dry run builds the same request as the node (`test_dry_run_builds_the_same_request_as_the_node`). The real tokens per case (at most 5,000) are measured by the author in S6 | test-engineer PASS, code-reviewer, grounding-evaluator PASS |
| P1.I2b.S5 | `human_checkpoint` records `status_at_checkpoint`; the `executed` entry uses it | `case_status_before` is `needs_human_review` after a review-path decision and `awaiting_decision` otherwise (`test_llm_failure_routes_to_needs_human_review_with_no_generated_text`, `test_resume_with_edited_message_...`, `test_draft_failure_...`) | test-engineer PASS, code-reviewer |
| P1.I2b.S6 | performed by the author after this session | commands and pass criteria below | author, grounding-evaluator, hitl-workflow-validator (GATE) |
| P1.I2b.S7 | this file, `current-state.md`, `current-plan.md` (plan changes entry), `roadmap.md`, ADR-018 status, ADR-019 and its index row, `assumptions.md` (A-25 updated, A-27 added) | Procedure in AGENTS.md section 5 | author |

## Token measurement (S4)

Method (ADR-019): the requests the nodes would send are built with the nodes' own functions (`nodes.build_request`, `nodes.build_case`, `prompts.*`) and counted with tiktoken `o200k_base`. Each count is system prompt plus user prompt plus strict response schema, plus 80 tokens of chat-format overhead per call. The overhead constant is calibrated on the Iteration 2 prompts. The "before" numbers come from running the unchanged Iteration 2 graph with the test fake adapter, the real hybrid retriever (read-only search on the development database) and an in-memory store, with no provider call. The estimate lands inside the 3,100 to 3,500 input tokens per call that the provider reported in the first real run.

| Case | Iteration 2 (before): calls, input tokens | Iteration 2b (after): calls, input tokens |
| --- | --- | --- |
| SC-03, approve | 3 calls: explain 3,087, propose 3,275, draft 3,251; **9,613** per case; 7 passages sent (8.6, 8.2, 8.3, SCH-B, 1.2, 8.0, DM-01) | 1 call: explain_propose 1,993; **1,993** per case; 4 passages sent (8.2, 8.3, SCH-B, DM-01) |
| SC-05, return | 3 calls: 3,238, 3,426, 3,407; **10,071** per case; 8 passages sent | 2 calls: explain_propose 2,005, draft 1,905; **3,910** per case; 4 passages sent (8.2, 8.3, SCH-B, DM-02) |
| SC-03, return (the first run's operator choice) | as SC-03 above | 2 calls: 1,993 + 1,887 (estimate before the last prompt rule was added); about 3,880 |
| SC-05, escalate | n/a | 2 calls: 2,005 + about 1,860 |

Notes:
- **Output tokens:** output tokens, including the model's reasoning, cannot be estimated offline. The 5,000 target counts input plus output. On SC-05 the estimate leaves about 1,090 tokens for the output of both calls. In the first run, three calls per case used about 10,000 tokens in total, of which about 9,600 were input, so outputs were small at `reasoning_effort=low`. The author's S6 run gives the real totals.
- **Draft prompt estimate:** the offline draft prompt uses a placeholder explanation of about 80 tokens. A real explanation may be longer.
- **Output cap:** the merged call's cap is 2,400 (twice the configured 1,200), because it returns two outputs in one object. A cap bounds the output; it is not spent unless used.

Commands: `uv run ptc showcase --scenario SC-03 --decision approve --dry-run` and `uv run ptc showcase --scenario SC-05 --decision return --dry-run` (offline; no database, no key, no provider call).

## S6: acceptance run (author)

Run from `backend/` with the free key in the root `.env` and the compose database up. Corpus chunks are not erased by the reset, and the corpus did not change in this iteration, so `ingest-corpus` is not needed. There is no new migration.

1. `docker compose -f ../deployment/docker-compose.yml up -d db`
2. `uv sync` (installs tiktoken, ADR-019)
3. `uv run ptc migrate` (expected: "applied migrations: none (up to date)")
4. `uv run ptc seed --reset` (erases cases, suggestions, decisions, the audit log and the checkpoints left by the first run, so SC-03 and SC-05 start clean)
5. `uv run ptc showcase --scenario SC-03 --decision approve`. **Pass:**
   - `explanation (LLM, valid)` and `proposal (LLM, valid)`, with no "needs human review" block.
   - The summary shows `status_after: approved` and `waiting_on: []`, with one LLM call (`explain_propose`).
   - The last line, `TOKENS PER CASE (SC-03): N`, shows N at most 5,000.
   - The audit trail ends with `decision` (stage `executed`, `case_status_before: awaiting_decision`) and `execution`.
6. `uv run ptc showcase --scenario SC-05 --decision return`. **Pass:**
   - The explanation and proposal are valid, and the proposal is `return`.
   - The block `draft for the return (LLM, valid)` shows a message with `for_action: return`, addressed to the crew member. It says what to correct or confirm on the day and that the correction is due before the payroll cut-off date, and it cites section 8.2.
   - The run stops at the message step (`waiting_on: ["message_checkpoint"]`).
   - The last line, `TOKENS PER CASE (SC-05): N`, shows N at most 5,000, over two LLM calls.
7. `uv run ptc confirm-message --case CASE-EMP-1002-20260314 --accept-draft` (after reading the draft printed in step 6; use `--message "..."` to send an edited text instead). **Pass:** the outcome shows status `returned`. The audit trail shows `decision` (stage `executed`, `message_source: draft_confirmed` or `draft_edited`, the original draft and the confirmed text) and `execution` with `return_message_id`. This step makes no LLM call.

Record for each scenario: the token line, the per-call input and output tokens from the summary, the attempts, and the rate-limit headers. If a run ends in `needs_human_review`, record the reason; the case can be rerun after another `ptc seed --reset`. Then run the grounding-evaluator on the printed outputs and the hitl-workflow-validator GATE.

## Validator findings and fixes applied

| Validator | Status | Summary and fixes applied |
| --- | --- | --- |
| hitl-workflow-validator, PRE on the ADR-018 design (first) | FAIL | Five majors: (1) a draft failure did not mark the case `needs_human_review` (constraint 7); (2) cancels and the first choice were not audited; (3) draft status could come from a cancelled round; (4) the showcase confirmed a draft the human had not seen; (5) execute was not idempotent. All five, and six minors, were resolved in the design before any graph code was written. |
| hitl-workflow-validator, PRE (second) | PASS | Five minors, applied in the design and the code: `stage` on every decision entry; at most one write per checkpoint node, after its interrupt; stalled checkpoints resume only with the accepted value; resumes serialized per thread; once `needs_human_review`, the case stays so; `confirm-message --actor`. |
| domain-consistency-validator (S1) | PASS | `hours_late` agrees across calc, schema, engine, oracle, manifest and domain model for every MEAL_PERIOD case: SC-03 0.5, SC-04 1.2 (two days), SC-14 0.8, SC-17 0.5, SC-05 and SC-18 0.0. No other fact changed, recomputed from the YAML. Fixes: ADR-018 names `hours_late`; the fact description has no digit; a test checks `hours_late` for every meal finding. |
| grounding-evaluator (S1, S2, S4) | PASS (harness absent until Iteration 3) | The passages sent for EV-03, EV-04 and EV-05 contain every expected key and support the claims; dropping 8.4, 7.4 and the other retrieved passages does not hurt the MEAL_PERIOD cases. Major fixed: citation keys in prose without brackets skipped validation; they are now extracted and validated, and the prompt forbids them. Minors fixed: the draft must cite the governing section; the stray-number allow-list uses exactly the case context shown; a test checks the passages sent for every wired case; proposal-part tests. |
| test-engineer | PASS | 196 passed at its run (210 after the fixes), ruff check and format clean, `ptc check` current, hooks 86 passed, both dry runs exit 0, no provider call. Minor fixed: tests for each check on the proposal part. |
| hitl-workflow-validator, GATE on code | PASS | Every checklist item holds with code evidence. Minors fixed: (1) the crash window between the execution commit and the audit (same as the code-reviewer major); (2) the showcase `--accept-draft` accepted an unseen draft, so the flag was removed from the showcase and kept only on `ptc confirm-message`; (3) `message_edited` is derived from `message_source`; `--message` with approve is rejected; a confirmation retry also compares the recipient. |
| code-reviewer | FAIL, then fixed | Major: a retry after a committed execution lost the `executed` audit entry. Fix: the `executed` and `execution` entries are now written inside the `apply_execution` transaction. Minors fixed: `message_edited`; allow-list from the shown context; `dry_run_requests` plus a test proving the dry run builds the node's request; tests for the message-step retries; `run_timecard` reads the case inside the lock; the calibration numbers are written in `tokens.py`; ADR-019 is indexed. |

## Re-validation

After the fixes above, the two validators that had raised a major or that guard the action path re-ran on the changed code.

| Validator | Status | Summary |
| --- | --- | --- |
| code-reviewer (re-review) | PASS | All seven fixes are correct and tested; no regression of ADR-008, ADR-009 or constraint 7. Minor fixed: unbracketed key matching had no boundaries ("CGMA-2026.1-8.21" read as 8.2); it is now anchored, and a key-shaped token that is not a well-formed key is reported as `unknown_key` (test added). Info carried forward: a retry of the same decision after a lost checkpoint is labeled `duplicate_attempt`. |
| hitl-workflow-validator (GATE re-confirmation) | PASS | The crash window is closed (the `executed` and `execution` entries are written in the execution transaction); the showcase never accepts a draft by itself; `message_edited` is consistent; the recipient is compared on retry; `run_timecard` reads the case inside the lock. The LLM has no write path, every action passes interrupt 1, and return and escalate also pass interrupt 2. Minors fixed: the overview's execute and audit contracts and its sequence now show the audit written with the effects; ADR-018 no longer says `audit` writes the `executed` entry; ADR-018 notes that a showcase `--message` is recorded as `draft_edited` when a valid draft existed. |

ADR-018 was set to Accepted after this re-validation (S3 and S4 done and validated, as the author required).

## Deviations from the plan

1. **New dependency `tiktoken` (ADR-019).** It was needed for the offline token measurement that the author required for this session. It is used only by `tokens.py` and the dry run. It downloads the `o200k_base` encoding (about 3.6 MB) on first use.
2. **S4 acceptance is split.** The before and after measurement in this session is an offline estimate; the measurement of record (provider-reported tokens per case, at most 5,000) is taken by the author in S6.
3. **The design gained rules beyond the original ADR-018 text**, all recorded in ADR-018 ("Implementation design" and "Rules added after the second PRE review"):
   - a `cancel` at the message step;
   - actor equality for confirmation;
   - `for_action` and the recipient check;
   - draft failure sets `needs_human_review`;
   - idempotent, audited execution;
   - `ptc confirm-message`;
   - unbracketed keys validated (anchored);
   - the draft must cite the governing section.
4. **The merged call's output cap is twice the configured cap** (`OUTPUT_CAP_FACTOR` in `nodes.py`), so the merged output is not truncated. Truncation is an `LLMError` and would route to review.
5. **No new migration.** The merged call is stored as the existing suggestion kinds `explain` and `propose`. The new audit stages live in the payload. The message step reuses the open case statuses.

## Validator findings carried forward

- **Tier 2 rubric for EV-05 (Iteration 3):** add "does not claim a meal penalty is owed". Section 8.2 says a short break is treated as if no meal was taken, and the stray-number check cannot catch a claim with no new number (grounding-evaluator).
- **Test literals:** `SECTION_KEY` and the passage lists are literals in the graph test modules, as in Iteration 2. Deriving them from `params` would follow ADR-007 more strictly (code-reviewer, minor). Do it when Iteration 5 widens the tests to six rules.
- **Draft subject:** the subject is validated but not carried to execution or the decision entry (code-reviewer, info). Decide in Iteration 4 whether the UI shows it; otherwise drop it from `DraftOutput` to save tokens.
- **Private LangGraph constant:** `_RESUME_CHANNEL` mirrors a private constant of LangGraph. A test pins it to the library value.
- **`--accept-draft` adopts the draft's suggested recipient** as the human's choice. This is documented in ADR-018.
- **The docs test checks node names, not edges** (hitl-workflow-validator, info).
- **Carried from Iteration 2:** the Anthropic adapter is untested; latency includes pacing; the integration database is single-process; human identity is self-asserted; the Iteration 3 harness recommendations (`iteration-002.md`).

## Metrics

| Metric | Value |
| --- | --- |
| Backend tests | 210 passed, 0 skipped (175 at the start; 7 integration tests against PostgreSQL) |
| Hook guard tests | 86 passed |
| Lint | ruff check and format clean |
| `ptc check` | all committed outputs are current |
| LLM calls per case | approve 1 (was 3); return or escalate 2 (was 3) |
| Estimated input tokens per case (offline) | SC-03 approve 1,993 (was 9,613); SC-05 return 3,910 (was 10,071) |
| Passages sent per MEAL_PERIOD case | 4 (was 7 or 8) |
| Real LLM calls in this session | 0 |
| Hygiene scans | em dashes, backspace bytes, AI attribution: none in changed files; non-ASCII none; the author runs the brand term scan |

## Open decisions raised or still open

- OD-09: the real-LLM acceptance run, P1.I2b.S6. Owner: author.
- OD-01, OD-02, OD-04, OD-10: unchanged (see `current-state.md`).
