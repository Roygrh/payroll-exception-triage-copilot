# Iteration 002b: Fixes from the first real run and token efficiency

Dates: 2026-10-10; 2026-10-14 (S6 recorded, S8, S8 re-run)
Status: closed on 2026-10-14. S8 was confirmed with the real model in the author's SC-05 re-run (4,741 tokens per case).
Phase: 1
Scope: Phase 1, Iteration 2b as defined in `docs/planning/current-plan.md` (steps P1.I2b.S1 to S8). S1 to S5 and S7 were built on 2026-10-10. S6, the acceptance with the real LLM, was run by the author on 2026-10-14 (results under "S6: acceptance run (author)"). S8 was built on 2026-10-14 to fix the meaning error that run found, and the author re-ran SC-05 on the S8 code the same day (results under "S8: re-run of SC-05 (author)"). No agent made a real LLM call: every test uses the fake adapter, and the token estimates are offline (ADR-019).

## Summary

The four problems found in the first real run (`iteration-002.md`, "Showcase run") are fixed in code and covered by tests, and the token cost per case is cut by about 60 to 80 percent on the offline estimate.

- **S1:** the engine computes `hours_late` (facts schema version 2) and the prompts forbid unit conversion and any number not given, so "0.5 hours" is now a fact rather than a stray number.
- **S2:** bracketed text that is not a citation key is rejected. Citation keys written without brackets are validated too.
- **S3:** the message is drafted after the human chooses return or escalate, for the action the human chose, and is confirmed or edited at a second checkpoint before execute (ADR-018). Approve makes no draft call. A draft failure marks the case `needs_human_review`, and the human writes the message.
- **S4:** explain and propose are one call. Only the finding's own sections and the case's deal memo are sent. Inputs are serialized compactly. The showcase prints the provider's tokens per case, and `--dry-run` estimates input tokens offline.
- **S5:** `case_status_before` in the decision audit entry is the status at the checkpoint.
- **S6 (2026-10-14, author):** the real-LLM acceptance passed: SC-03 used 2,317 tokens per case and SC-05 4,732. The run also exposed a meaning error, "12.0 minutes" for the clock time of meal out.
- **S8 (2026-10-14):** prompts show timecard times as HH:MM, and validation checks what a number means, not only that it is present: units, clock times, and clock times written as durations.
- **S8 re-run (2026-10-14, author):** SC-05 return passed on the real model with 4,741 tokens per case. Every check list was empty, times appeared only as HH:MM and the "12.0 minutes" error did not recur. One quality finding (the correction asks the crew member to change accurate times to meet the minimum) is carried to the Iteration 3 tier 2 rubric.

Iteration 2b is closed. The next iteration is 4 (UI).

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
| P1.I2b.S6 | author's real-LLM run on 2026-10-14, recorded under "S6: acceptance run (author)" | SC-03 approve: approved, 2,317 tokens per case; SC-05 return: valid draft for the return, 4,732 tokens per case; confirmation returned the timecard with no LLM call; both within 5,000. The meaning error found in this run is fixed in S8 | author; the S8 validators below reviewed the code the run exposed |
| P1.I2b.S8 | `calc.clock_time`; `engine/facts.py` (units, `fact_units`); `graph/prompts.py` (`times_of_day` in HH:MM, units in the fact names, prompt rule, version `2026-10-14.1`); `graph/nodes.py` (`unit_mismatches`, `unknown_clock_times`, `clock_times_with_unit`, clock times removed from the presence check); tests; `overview.md` | The S6 sentence and its HH:MM form are rejected in the explanation, the proposal and the draft; the required correct uses pass; the stray-number check still works (`test_iteration_2b.py`, S8 section; `test_calc.py`); 217 tests pass with `test_db.py` excluded; `ptc check` green; dry run SC-03 2,029, SC-05 3,982. Confirmed with the real model in the author's SC-05 re-run of 2026-10-14: all checks passed, 4,741 tokens per case | test-engineer PASS, code-reviewer FAIL then PASS, grounding-evaluator PASS, hitl-workflow-validator GATE PASS; author re-run PASS |
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

Run by the author on 2026-10-14 from `backend/`, with the free key in the root `.env`. Steps:

1. `docker compose -f ../deployment/docker-compose.yml up -d db`
2. `uv sync`
3. `uv run ptc migrate`: applied migrations: none (up to date).
4. `uv run ptc seed --reset`: 10 deal memos, 22 timecards.
5. `uv run ptc showcase --scenario SC-03 --decision approve`
6. `uv run ptc showcase --scenario SC-05 --decision return`
7. `uv run ptc confirm-message --case CASE-EMP-1002-20260314 --accept-draft`

Results:

| Step | Result | Detail |
| --- | --- | --- |
| SC-03, `--decision approve` | PASS | One LLM call (`explain_propose`): input 1,970, output 347, **total 2,317 tokens**, 1 attempt. Explanation and proposal valid; the proposal equals the policy. Status approved, premium 8.25 USD, timecard Ready for approver 2. Audit: `suggestion`, `validation`, `decision` (stage `executed`, `case_status_before: awaiting_decision`), `execution`. |
| SC-05, `--decision return` | PASS on the checks of that time | Two LLM calls: `explain_propose` 1,982 input + 399 output, `draft` 1,963 input + 388 output; **total 4,732 tokens**, 1 attempt each. The draft was valid, with `for_action: return` and recipient employee, and it cited 8.2. The run stopped at `message_checkpoint`. |
| `confirm-message --accept-draft` | PASS | Status returned, timecard Rejected, `message_source: draft_confirmed`; no LLM call. |

- **Tokens:** the target of at most 5,000 per case is met for both cases. The offline estimate held: SC-03 1,993 estimated against 1,970 reported, SC-05 3,910 against 3,945 (A-27 confirmed).
- **Meaning error found by the author:** in SC-05 both the explanation and the confirmed draft said "the meal out at 12.0 minutes after Call". 12.0 is the clock time of meal out (12:00 in decimal hours); hours to meal was 5.0. The stray-number check passed it because 12.0 is in the case data: that check tests whether a number is present, not what it means. Fixed in S8 (below). The author re-ran SC-05 on the S8 code and the error did not recur ("S8: re-run of SC-05 (author)").

## S8: unit and clock-time meaning check

Step P1.I2b.S8, added on 2026-10-14 (plan changes entry of that date). No LLM call was made in this session.

- **Prevent:**
  - `calc.clock_time` formats a timecard event as a time of day in HH:MM. A wrap past midnight is marked "next day", so 26.5 becomes "02:30 next day". A negative time raises an error.
  - `prompts.case_context` shows each day with findings as `times_of_day` (call, meal out, meal in, wrap in HH:MM) and never as decimal hours.
  - Each duration fact declares its unit in `engine/facts.py` (`fact_units`; names, values and the facts schema version are unchanged). The fact names block shows the unit, for example `MEAL_PERIOD.hours_to_meal (hours):`.
  - The system prompt says timecard times are times of day, to be written exactly as shown and never with minutes or hours. Prompt version `2026-10-14.1`.
- **Detect** (`graph/nodes.py`, `_check_output`, applied to the explanation, the proposal and the draft):
  - **Unit check:** a number written with minutes or hours must equal a fact of that unit, or appear with that unit in a passage that was sent. Accepted forms: "N-minute"; min, mins, hr, hrs and h; no space before the unit; Unicode hyphens.
  - **Clock-time check:** an HH:MM time (seconds allowed) must be an event of a day with findings.
  - **Duration check:** a clock time written as a duration ("12:00 minutes") is always rejected. This closes the same error in the HH:MM form the prompts now use; the code-reviewer found it.
  - **Presence check tightened:** clock times are removed before numbers are extracted. "12:00" in the case context therefore no longer allows a bare 12, and a bare "12.0" with no unit is a stray number unless a cited passage holds a 12. The grounding-evaluator found this gap.
  - Any failure marks the output invalid and routes the case to `needs_human_review`, with a reason that names the number and the unit, for example `explain: numbers with a unit that match no fact or sent passage with that unit: ['12.0 minutes']`. A draft failure hides the draft, and the human writes the message (constraint 7).
- **Tests** (fake adapter):
  - `test_the_s6_sentence_routes_to_review_in_every_output` rejects the exact S6 sentence and its HH:MM form in each of the three outputs.
  - `test_the_s6_sentence_fails_the_meaning_check_and_clock_times_allow_no_bare_number` shows the meaning check and the tightened presence check on the S6 case data.
  - `test_correct_units_and_clock_times_pass` accepts "24 minutes", "24-minute", "30 minutes", "5.0 hours", "6.0 hours", "0.5 hour", "6.5 hours", "12:00" and "12:24" in correct use. The agreement values come from the YAML.
  - `test_unknown_clock_times_and_stray_numbers_still_route` covers an unknown clock time and shows the stray-number check still works.
  - The other new tests are: `test_prompts_show_times_of_day_in_hh_mm_and_fact_units`, `test_unit_numbers_are_read_with_their_unit`, `test_a_unit_number_is_allowed_by_a_sent_passage_with_that_unit_only` and `test_clock_time_is_a_time_of_day_in_hh_mm`.
- **Offline dry run** (`uv run ptc showcase ... --dry-run`):

| Case | Before S8 (estimate of 2026-10-10) | After S8 | Reported in S6 (before S8) |
| --- | --- | --- | --- |
| SC-03, approve | 1,993 | **2,029** (one call) | 1,970 input, 2,317 total |
| SC-05, return | 3,910 | **3,982** (2,041 + 1,941) | 3,945 input, 4,732 total |

  The increase comes from the HH:MM strings, the units in the fact names and one prompt sentence. With the S6 output tokens, SC-05 should land near 4,800 tokens per case, under the 5,000 target.
- **Known gaps** (carried forward):
  - Number words ("thirty minutes", "half an hour") are not checked.
  - A bare number with no unit still passes on presence when a cited passage holds the same number.
  - The unit check tests whether a (value, unit) pair is allowed, not which fact a number describes. For example, "the meal lasted 6.0 hours" passes on SC-05 because 6.0 hours is the deadline. This belongs to the tier 2 faithfulness rubric.
  - Times written in a.m./p.m. form, "07:00 hours" and derived values ("6 minutes short") route to review: the check fails closed, as ADR-008 intends.

## S8: re-run of SC-05 (author)

Result: **PASS**. Run by the author on 2026-10-14 from `backend/`, with the free key in the root `.env`, on the S8 code. No dependency, migration or corpus changed in S8, so `uv sync`, `ptc migrate` and `ptc ingest-corpus` were not needed.

Commands run:

1. `uv run ptc seed --reset` (database reset: erased the cases, suggestions, decisions, audit log and checkpoints of the S6 run, and reloaded 10 deal memos and 22 timecards, so SC-05 started clean)
2. `uv run ptc showcase --scenario SC-05 --decision return`
3. `uv run ptc confirm-message --case CASE-EMP-1002-20260314 --accept-draft`

Results:

| Item | Result | Detail |
| --- | --- | --- |
| `explain_propose` call | PASS | Input 2,018, output 459, total 2,477; 1 attempt |
| `draft` call | PASS | Input 2,050, output 214, total 2,264; 1 attempt |
| Tokens per case | PASS | `TOKENS PER CASE (SC-05): 4,741` (input 4,068, output 673, 2 calls); within the 5,000 target |
| Validation | PASS | Explanation, proposal and draft valid. Every check list empty: `stray_numbers`, `unit_mismatches`, `unknown_clock_times`, `clock_times_with_unit`, `pseudo_references`, `required_missing`. `proposal_matches_policy: true`. No `needs_human_review` |
| Meaning | PASS | Times written only as HH:MM (07:00, 12:00, 12:24). Numbers with units only 24 minutes, 30 minutes, 5.0 hours and 6.0 hours (also as "24-minute" and "6.0-hour"). The S6 error ("12.0 minutes") did not recur. The explanation now reads: a call at 07:00 and a meal out at 12:00, giving 5.0 hours to the meal |
| Draft | PASS | `for_action: return`, recipient employee, cites CGMA-2026.1-8.2, states the payroll cut-off date 2026-03-17 |
| `confirm-message --accept-draft` | PASS | Status `returned`, timecard Rejected, `message_source: draft_confirmed`, no LLM call. Audit entries 5 (`decision`, stage `executed`) and 6 (`execution`) |
| Offline estimate | holds | 3,982 input tokens estimated before the run, 4,068 reported (about 2 percent higher; A-27) |

Quality finding (no wrong number, so no code check fails; carried to the Iteration 3 tier 2 rubric, no code change now): the proposal's `requested_correction` said "If the times are correct, extend the meal duration to at least 30 minutes", and the draft said "adjust them so the break is at least 30 minutes". Both ask the crew member to change accurate time records to meet the minimum. See "Validator findings carried forward".

The pass criteria set before the run were:
- In the explanation, the proposal and the draft, every number written with "minutes" or "hours" is a fact with that unit: 24 minutes (meal), 30 minutes (minimum), 5.0 hours (to meal), 6.0 hours (deadline), or 0 minutes and 0.0 hours late.
- Timecard times, if written at all, appear as HH:MM (07:00, 12:00, 12:24, 15:30).
- The outputs are marked `(LLM, valid)` and no "needs human review" block appears. The block `draft for the return (LLM, valid)` shows `for_action: return` and cites section 8.2. The run stops at `message_checkpoint`.
- `TOKENS PER CASE (SC-05): N` shows N at most 5,000.
- `confirm-message` ends with status `returned` and `message_source: draft_confirmed`.

All of them were met.

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

## S8 validation (2026-10-14)

No LLM call and no database write: pytest ran with `tests/test_db.py` excluded, and the dry runs are offline.

| Validator | Status | Summary and fixes applied |
| --- | --- | --- |
| hitl-workflow-validator, GATE | PASS | No graph edge, node or write path changed. Every unit, clock-time or duration failure routes to `needs_human_review` with a named reason, and a failed draft is hidden so the human writes the message (constraint 7). Minors fixed: clock times written with a unit are now detected; the prompt says to write times exactly as shown. Minor carried forward: a.m./p.m. times route to review (fails closed). |
| test-engineer | PASS | 214 passed at its run (217 after the fixes), ruff clean, `ptc check` current, hook suite 86 passed, both dry runs exit 0. |
| code-reviewer | FAIL, then PASS | Major: "12:00 minutes" passed every check, because the unit check skips numbers inside clock times and 12:00 is a case event. Fixed with `clock_times_with_unit` and tests in all three outputs. Minors fixed: min, mins, hr and hrs read; HH:MM:SS compared by HH:MM; the agreement values in the tests come from the YAML; `clock_time` rejects negative input. Re-review PASS. A second re-check after the grounding fixes also passed: the character classes and lookbehind are correct, and a negative test for non-unit words was added. Minor carried forward: "2 HR contacts" would read as hours and route to review (fails safe). |
| grounding-evaluator | PASS | EV-03, EV-04 and EV-05 send the same passages, with every expected key. All faithful unit phrasings of the facts and of 8.2, 8.3 and SCH-B are allowed. The S6 sentence and its variants are rejected, and no decimal-hour event remains in the prompt. Minors fixed: HH:MM parts no longer allow a bare number; no-space units, "h" and Unicode hyphens are read. Minors carried forward: number words; which fact a number describes; deadline clock times. |

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
6. **New step S8 (2026-10-14).** It was added after the S6 run (plan changes entry of that date). Two checks went beyond the step text, from validator findings: the duration check ("12:00 minutes") and clock times removed from the presence check. No ADR changed. The S8 checks implement the runtime check that ADR-008 already requires (no number unless it is present in the facts or passages), now applied to the number's meaning as well.

## Validator findings carried forward

- **S8 re-run, quality finding, to the Iteration 3 tier 2 rubric (author, 2026-10-14):**
  - On SC-05 the proposal's `requested_correction` said "If the times are correct, extend the meal duration to at least 30 minutes", and the draft said "adjust them so the break is at least 30 minutes". Both ask the crew member to change accurate time records to meet the minimum.
  - Rubric criterion to add: for a short meal, the return message and the requested correction must ask to confirm the recorded times or correct them to the actual times; they must never ask to change accurate times to meet the minimum.
  - Code checks cannot detect this, because no number is wrong. In Iteration 3, if the baseline shows it again, decide whether to add a prompt instruction. No code change now.
- **S8, to the Iteration 3 tier 2 rubric:**
  - Number words ("thirty minutes", "half an hour") are not checked.
  - Each quantity must be attributed to the right fact and event: "the meal lasted 6.0 hours" passes the unit check on SC-05.
  - Times written in a.m./p.m. form are not recognized.
- **S8, review counts:** in the Iteration 3 baseline, count review routings by S8 reason. If the model often writes deadline clock times ("the deadline was 13:00") or "07:00 hours", add an engine fact such as the deadline as a time of day; do not loosen the check (grounding-evaluator).
- **S8, the UI (Iteration 4):** show timecard times as HH:MM, as the prompts do.

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
| Backend tests | 210 passed, 0 skipped on 2026-10-10 (175 at the start; 7 integration tests against PostgreSQL). After S8: 217 passed with `test_db.py` excluded (not run, to avoid database writes; the 7 integration tests do not touch the changed code), 224 in total |
| Hook guard tests | 86 passed |
| Lint | ruff check and format clean |
| `ptc check` | all committed outputs are current |
| LLM calls per case | approve 1 (was 3); return or escalate 2 (was 3) |
| Estimated input tokens per case (offline) | SC-03 approve 1,993 (was 9,613), 2,029 after S8; SC-05 return 3,910 (was 10,071), 3,982 after S8 |
| Reported tokens per case (S6, provider) | SC-03 approve 2,317 (1,970 input, 347 output); SC-05 return 4,732 (3,945 input, 787 output) |
| Reported tokens per case (S8 re-run, provider) | SC-05 return 4,741 (4,068 input, 673 output; `explain_propose` 2,477, `draft` 2,264); estimate 3,982 input, about 2 percent under the reported input |
| S8 checks on the real model (SC-05 re-run) | all passed: no stray number, unit mismatch, unknown clock time, clock time with a unit, pseudo-reference or missing required key; proposal equals the policy |
| Passages sent per MEAL_PERIOD case | 4 (was 7 or 8) |
| Real LLM calls by agents | 0 (S6 and S8 re-run calls were made by the author) |
| Hygiene scans | em dashes, backspace bytes, AI attribution: none in changed files; non-ASCII none; the author runs the brand term scan |

## Open decisions raised or still open

- OD-09: closed on 2026-10-14 (S6 passed).
- No new decision. The S8 re-run passed, and Iteration 2b is closed. Whether to add a prompt instruction for the quality finding is decided in Iteration 3, after the baseline.
- OD-01, OD-02, OD-04, OD-10: unchanged (see `current-state.md`).
