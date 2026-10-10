# Iteration 002: Vertical slice MEAL_PERIOD end to end

Dates: 2026-10-08
Phase: 1
Scope: Phase 1, Iteration 2 as defined in `docs/planning/current-plan.md` (steps P1.I2.S1 to S8), plus the carried-forward work from Iteration 1. No UI, no evaluation harness, no tracing.

## Summary

The slice exists in code and runs against the compose database: the rule engine detects MEAL_PERIOD findings and computes every fact (tested fact by fact against the committed manifest), the code-owned policy decides the action, hybrid retrieval over the agreement and the deal memos returns the governing passages, the LLM adapter v1 (OpenAI-compatible, default gpt-oss-20b on GroqCloud) produces explanation, proposal and draft as strict JSON, code validates citations, stray numbers and the proposal against the policy, the LangGraph run pauses at the human checkpoint on a PostgreSQL checkpointer, resumes with the human's decision, executes it in one transaction under the human's identity and writes an append-only audit trail; a FastAPI API exposes demo steps 1 to 3. The suite grew from 102 to 175 tests (including 7 integration tests against PostgreSQL), all validators returned PASS at the gate, and `ptc check` is green.

**The real-LLM acceptance of P1.I2.S5 is not yet met and moves to Iteration 2b.** At the end of the build the `GROQ_API_KEY` in the root `.env` was rejected by the provider (HTTP 401). On 2026-10-08 the author ran the slice with a valid key (see "Showcase run" below): the smoke call succeeded (P1.I2.S4 acceptance met), and the SC-03 showcase validated its citations, matched the proposal to the policy, paused at the human checkpoint, resumed, executed and audited. The case was nevertheless routed to `needs_human_review` because the model converted 30 minutes into "0.5" hours, which the stray-number check rejected as designed (ADR-008). The run also exposed a draft-versus-decision gap, bracketed pseudo-references in the explanation, an audit field error and a token cost of about 10,000 tokens per case. Iteration 2b (`docs/planning/current-plan.md`) fixes these and repeats the acceptance run; ADR-018 (Proposed) records the graph change.

## Author decisions recorded at the start of the iteration

- OD-06 closed: article 2 text stands.
- OD-07 closed: penalty schedule 8.25 / 11.00 / 13.75 kept.
- OD-08 closed: the guild local number was removed everywhere (YAML, schema, template, rendered agreement, deal memos, catalog, filler memos, domain model); regenerated with `ptc`, `ptc check` green.
- ADR-016 (new) supersedes ADR-002 on the provider choice: default LLM gpt-oss-20b on GroqCloud (free tier) through an OpenAI-compatible adapter; OpenAI, a local Ollama server and other compatible endpoints by configuration; Anthropic optional behind the same v1 interface; single root `.env` (template `.env.example`, Groq variables uncommented with the key empty, Anthropic block commented, `DATABASE_URL` uncommented); client-side pacing and retry with backoff.
- ADR-017 (new): local open-source embeddings (BAAI/bge-small-en-v1.5 via fastembed, 384 dimensions, about 67 MB, MIT license, downloaded on first run) and hybrid retrieval (pgvector cosine plus PostgreSQL full-text) fused by reciprocal rank fusion.
- Documents updated for ADR-016 and ADR-017: ADR-002 status, `docs/decisions/README.md`, `docs/requirements/project-brief.md`, `docs/architecture/overview.md`, `README.md`, `backend/README.md`, `.env.example`, `docs/planning/current-plan.md` (P1.I2.S3, S4, S5), `docs/evidence/assumptions.md` (A-07, A-18, A-22 updated; A-25, A-26 added), `docs/evidence/synthetic-data-methodology.md`.

## Carried forward from Iteration 1 (done first)

- `backend/src/payroll_triage/timecards.py`: shared `Timecard` and `TimecardDay` (round trip to JSON, `work_days`, `missing_entries`, `is_no_meal_day`). The generator, the oracle, the engine and the store use it.
- `backend/src/payroll_triage/policy.py`: the ADR-009 table (`Situation` rows, `POLICY_TABLE`, `POLICY_ROW_TEXT`), `meal_situation`, `premium_situation`, `completeness_situation`, `compliance_situation`, `day_is_plausible`, `combined_action`; `tests/test_policy.py` has one test per row plus combination and plausibility. The oracle (`evals/expectations.py`) and the engine both call it.
- "Dismissed before the meal deadline" exception (agreement 7.4 last sentence and 8.7): `TimecardDay.is_no_meal_day` (meal out = meal in = wrap and elapsed day within the deadline) is honored by the oracle's `meal_findings` and by the engine's MEAL_PERIOD rule; `tests/test_timecards.py` covers the exception, the same recording past the deadline (stays a short meal, returned) and equal meal entries before wrap (short meal).

## Steps completed

| Step | Artifact | Acceptance evidence | Validators |
| --- | --- | --- | --- |
| P1.I2.S1 | `deployment/docker-compose.yml` (pgvector/pgvector:pg16, api service), `deployment/Dockerfile.api`, `backend/src/payroll_triage/db/migrations/0001_initial.sql`, `db/migrate.py` (`ptc migrate`), `db/connection.py`, `db/seed.py` (`ptc seed [--reset]`) | `docker compose up db` healthy (pgvector 0.8.6); `ptc migrate` creates 15 application tables, the audit triggers and the four LangGraph checkpoint tables (`test_migration_creates_all_tables_including_checkpoints`); seed loads 10 memos and 22 timecards | test-engineer PASS |
| P1.I2.S2 | `engine/rules.py` (MEAL_PERIOD, `detect`), `engine/facts.py` (`MealPeriodFacts`), `engine/priority.py`, `policy.py`, `timecards.py`, `queue` block in `data/rule-parameters.yaml` and schema, `tests/test_engine.py`, `test_policy.py`, `test_timecards.py` | Engine findings equal the manifest's MEAL_PERIOD findings fact by fact for all 18 cases (SC-03 approve 1 increment 8.25; SC-04 approve 3 increments per day; SC-05 return, short meal); clean weeks and filler produce nothing; policy table tested per row; priority formula from the YAML | test-engineer PASS, code-reviewer PASS (after fixes) |
| P1.I2.S3 | `retrieval/chunker.py` (96 agreement chunks plus one per deal memo), `retrieval/embeddings.py`, `retrieval/index.py` (`ptc ingest-corpus`, 106 chunks), `retrieval/search.py` (hybrid, RRF), `retrieval/citations.py`, `tests/test_retrieval.py`, `tests/test_db.py` | The graph's MEAL_PERIOD query returns section 8.2 in the top 3 and Schedule B in the top 6 with the real embedder; the deal memo query returns DM-01 in the top 3; every citation key resolves to its passage (`test_corpus_chunks_match_the_pure_chunker`) | grounding-evaluator (spot check, see gate), test-engineer PASS |
| P1.I2.S4 | `llm/v1/` (interface, pacing, openai_compatible, anthropic_adapter, factory), `config.py`, `tests/test_adapter.py`, `ptc smoke-llm` | Interface documented in the package docstring and ADR-016; fake adapter only under `tests/support/`; transport, pacing, retry on 429 with retry-after, strict schema body, json_object fallback and key resolution tested; real smoke call attempted: 401 from the provider (key invalid, see Summary) | code-reviewer PASS (after fixes) |
| P1.I2.S5 | `graph/` (state, prompts with strict schemas, nodes, build, execute, service), `tests/test_graph.py`, `tests/test_graph_paths.py` | With the fake adapter on SC-03: validated citations, proposal equal to policy, pause at `human_checkpoint`; forced LLM failure, invalid citation, stray number, proposal mismatch and empty retrieval each route to `needs_human_review` with no generated text; the real-LLM run is blocked by the key | hitl-workflow-validator PASS (POST and gate), grounding-evaluator (see gate) |
| P1.I2.S6 | `human_checkpoint` (LangGraph `interrupt`), `execute`, `audit`, `PostgresSaver` on the app database, audit triggers | `test_graph_checkpoint_survives_a_rebuild`: pause with one graph instance, resume with a second instance on the same database, checkpoint ids before and after differ; the edited message is what executes and the original draft is in the decision audit entry; UPDATE, DELETE and TRUNCATE on `audit_log` are rejected by the database | hitl-workflow-validator PASS (gate), test-engineer PASS |
| P1.I2.S7 | `api/app.py` (`POST /ingest`, `GET /queue`, `GET /cases/{id}`, `POST /cases/{id}/decide`, `GET /cases/{id}/audit`, `GET /passages/{key}`), `runtime.py`, `ptc serve`, `tests/test_api.py` | Demo steps 1 to 3 performed over the API on the seeded week with the fake adapter (`test_demo_steps_one_to_three_over_the_api`) and manually against the real database and the real adapter (ingest of 2026-03-14: 10 timecards, 2 cases, 8 clean; queue in priority order; passage lookup; decide returns 422 without a message and 409 after the case is decided) | test-engineer PASS, code-reviewer PASS (after fixes) |
| P1.I2.S8 | this file, `current-state.md`, `current-plan.md` (plan changes entry), `docs/architecture/overview.md` (C4 level 3 and sequence diagram) | Procedure in AGENTS.md section 5 | author |

## Validator findings and fixes applied

Gate run on the final state (2026-10-08). The five validator subagents are registered in this session and were invoked directly.

| Validator | Status | Summary and fixes applied |
| --- | --- | --- |
| test-engineer | PASS | 166 passed at the first gate run (175 after the review fixes), 0 skipped; ruff check and format clean; `ptc check` current; hook suite 86 passed; integration tests ran against the database. Minor: the shared test database was not safe for concurrent pytest processes; fixed with a PostgreSQL advisory lock held for the module. |
| code-reviewer | FAIL, then PASS after fixes (two rounds) | Majors fixed: the decision row and the effects of the human decision are now written in one transaction (`apply_execution`; a failing plan writes nothing, tested); `ptc showcase` no longer defaults the decision to the policy action nor composes a return message in code (`--decision` required; a return sends `--message` or the validated draft verbatim, otherwise stops; tested); the execute retry path is tested and refuses a different decision than the one stored in the thread. Minors fixed: urgency honors holidays; intake status, post-decision statuses and the demo approver come from the scenario catalog; the stray-number allow-list uses the facts' values, the case context and the cited passages plus the finding's own sections (recorded in ADR-008); the draft prompt no longer asks for a word count; a case left in `detected` by a non-LLM exception is resumed on the next ingest; a thread stuck at `execute` or `audit` can be retried; the overview describes the OR full-text query; test hygiene items. Open (info): adapter latency includes pacing wait; the Anthropic adapter is untested. |
| hitl-workflow-validator | PASS (POST on code and GATE, re-confirmed after the review fixes) | All seven checks hold with code evidence: writes only through `apply_execution` after the interrupt with the human as actor; the interrupt is unconditional and no flag skips it; no template produces explanation, proposal or draft text; proposal mismatch routes to review without overwrite; resume uses the stored thread and executes the human's edited message with the original draft in the audit log; audit log append-only (UPDATE, DELETE and TRUNCATE rejected; the demo reset is the documented exception); the architecture document names the same nodes and edges. Minors fixed: checkpointer mandatory; escalation note source recorded; `output_status` per LLM output in the case detail and the showcase; stale section references. |
| domain-consistency-validator | PASS | Every number, section, scenario, action and deal memo agrees across the YAML, the agreement, the memos, the generated data, the manifest, the domain model, the engine and the prompts; the guild local number is gone from every non-historical file; no brands, no em dashes, no copied text. Minors fixed: the citation example in the system prompt is a neutral placeholder; the severity order sentence is derived from the policy module; section 8.3 no longer repeats the same ordinal; the methodology no longer mentions local numbers; one definition of the work day label. Info: a no-meal day recorded past the deadline has no scenario (carried forward). |
| grounding-evaluator | PASS (harness absent, expected until Iteration 3) | Stand-in deterministic suite passed; citation existence, version, deal memo scoping, required section and proposal equality are enforced in code and tested; hand spot checks of EV-03, EV-04 and EV-05 against sections 8.2, 8.3, 8.7, 7.4 and Schedule B and deal memo DM-01: every expected key supports the claims the prompts ask for; failure paths route to review with facts only. Minor fixed: the explanation must now cite the governing section of every finding, not only the first. Its major concerned concurrent validators sharing the test database (fixed with the advisory lock). Open: the real-LLM run (one smoke call attempted, 401). Recommendations for Iteration 3 recorded below. |


## Deviations from the plan

1. **The real-LLM acceptance of P1.I2.S5 is not met; it moves to Iteration 2b.** During the build the key was invalid (HTTP 401; the graph routed the cases to `needs_human_review` as designed). The author's run with a valid key on 2026-10-08 is recorded under "Showcase run": the pipeline worked end to end, but SC-03 ended in `needs_human_review` (stray number "0.5"), so the condition "validated citations and a proposal equal to the policy" without review is not yet demonstrated. Iteration 2b, step P1.I2b.S6, repeats the acceptance (plan changes entry of 2026-10-09).
2. **Groq free-tier limits read from the live headers on 2026-10-08:** 1,000 requests per day and 8,000 tokens per minute for `openai/gpt-oss-20b` on the author's account. These match the provider's public base table (verified the same day); the daily token limit is not reported in the headers. Recorded in ADR-016.
3. **hitl-workflow-validator PRE on the design was not run as a separate step** before the graph was coded; the POST run on the code and the gate run cover the same seven checks (both PASS). Recorded in the plan changes.
4. **Queue priority moved from P1.I2.S7 to P1.I2.S2** with its weights in the YAML `queue` block (ADR-007); OD-01 remains open for the author to confirm the weights.
5. **Section count:** the chunker finds 96 anchored headings; Iteration 1 reported 97 (that count included the document title). Nothing changed in the corpus except the OD-08 wording and the 8.3 ordinal fix.
6. **Agreement wording fix (domain validator minor):** section 8.3 repeated the same ordinal twice; the template now reads "each listed increment at the amount listed for it, and the third and every later increment at the last amount". Re-rendered; `ptc check` green; corpus re-ingested.
7. **Dependencies added** (ADR-015 procedure): langgraph, langgraph-checkpoint-postgres, psycopg[binary,pool], pgvector, httpx, anthropic (optional adapter), fastembed, python-dotenv, uvicorn. The `openai` SDK is not used: the OpenAI-compatible adapter is plain HTTP.

## Showcase run

Run by the author on 2026-10-08 with `openai/gpt-oss-20b` on GroqCloud (free tier), from `backend/`. Recorded from the author's report of the console output; the raw output is not committed.

**`uv run ptc smoke-llm`:** succeeded. Live rate-limit headers: 1,000 requests per day, 8,000 tokens per minute.

**`uv run ptc showcase --decision return` on SC-03** (expected facts: hours to meal 6.5, minutes late 30, 1 increment, 8.25 USD; policy action approve):

| Check | Result |
| --- | --- |
| Citations | Valid (the citation validator accepted every key) |
| Proposal versus policy | Equal (approve) |
| Human checkpoint, resume, execute, audit | Worked: paused, resumed from the stored thread, executed under the human's identity, audit entries written |
| Final routing | `needs_human_review`: the explanation and the proposal both wrote "0.5" (the model converted 30 minutes into hours); "0.5" is not among the facts, the case context or the passages, so the stray-number check rejected both outputs. Correct behavior under ADR-008; the cause is a missing fact and a prompt that does not forbid unit conversion |
| Tokens | About 10,000 tokens per case across the three calls (explain, propose, draft), each with about 3,100 to 3,500 input tokens. The draft call needed a retry because the per-minute token budget (8,000) was exhausted; the retry with backoff succeeded |

Findings from the run (each becomes a step of Iteration 2b):

1. **Unit conversion by the model** (stray "0.5"). Fix: the engine computes `hours_late` as a fact; prompts forbid unit conversion and any number not given (P1.I2b.S1).
2. **Operator error that revealed a real gap.** The run used `--decision return` on an approve case. When the human's action differs from the proposal, the draft written for the proposed action is sent unchanged: the return carried a message drafted for an approval. Fix: draft after the human decision, for the action the human chose, only for return and escalate (ADR-018, P1.I2b.S3).
3. **Bracketed pseudo-references.** The explanation contained text such as "[MEAL_PERIOD facts: ...]" that looks like a reference but is not a citation key; the citation validator does not reject it today. Fix: validation rejects bracketed references that are not citation keys; prompts forbid them (P1.I2b.S2).
4. **Audit field error.** The decision audit entry recorded `case_status_before = returned` instead of `needs_human_review`. Fix in P1.I2b.S5.
5. **Token cost.** About 10,000 tokens per case exceeds the 8,000 tokens-per-minute budget for a single case and forces retries. Fix: limited passages, merged explain and propose, compact serialization; target at most 5,000 tokens per MEAL_PERIOD case (ADR-018, P1.I2b.S4).

Acceptance of P1.I2.S5 with the real LLM is therefore not met in Iteration 2; P1.I2b.S6 repeats it: SC-03 with `--decision approve` must end approved without `needs_human_review`, and SC-05 with `--decision return` must produce a correction message drafted for the return.

## Validator findings carried forward

- Latency recorded by the adapter includes the pacing wait and the retry backoff (code-reviewer, info): measure per attempt when tracing arrives in Iteration 6.
- The Anthropic adapter is untested (no key, no mocked client test); it is optional (ADR-016) and mirrors the OpenAI-compatible one. Add a mocked test when a second provider is wired in Phase 2 (P2.I7).
- The integration suite uses one fixed test database (`ptc_test`); only one pytest process may run it at a time (documented in the test module).
- A no-meal day recorded past the deadline (meal out = meal in = wrap, elapsed day longer than the deadline) is treated as a short meal and returned; no scenario covers it (domain validator, info). Decide in Iteration 5 if a scenario is added.
- Human identity is self-asserted in the request body (no authentication in Phase 1, documented); Phase 2 decision.
- The UI (Iteration 4) must use `output_status` from the case detail so that an invalid or unvalidated LLM output is never shown as validated.
- `test_params.py` pins the YAML design values as literals (the ADR-007 "YAML equals the domain model" guard); keep it the only such module.
- Iteration 3 harness (grounding-evaluator): check the verbatim passage text for every expected key over all 106 chunks (the runtime validator checks key resolution, which is right at runtime but not sufficient for tier 1 rule 2); make the judge rubric treat a short-meal explanation that cites 8.3 or Schedule B to justify a penalty as unfaithful; consider expected keys per situation (short meal: 8.2 only) rather than per rule; add a negative scenario for dismissal before the meal deadline so tier 1 rule 4 covers that branch.
- Retry comparison ignores `recipient_role` (code-reviewer, info); the stored plan executes regardless.

## Metrics

| Metric | Value |
| --- | --- |
| Backend tests | 175 passed, 0 skipped (19 files; 7 integration tests against PostgreSQL) |
| Hook guard tests | 86 passed |
| Lint | ruff check and format clean |
| Corpus | 96 agreement chunks + 10 deal memo chunks = 106 rows, 384-dimension vectors |
| Embedding model | BAAI/bge-small-en-v1.5 via fastembed 0.9.0, about 67 MB (quantized ONNX), downloaded once |
| Real LLM calls during the build | 5 (probe, smoke, two cases on ingest, smoke by the grounding evaluator); all rejected with 401 (invalid key) |
| Real LLM run by the author (2026-10-08) | smoke succeeded; SC-03 showcase: 3 structured calls plus 1 retry on the draft (per-minute token budget), about 10,000 tokens per case, about 3,100 to 3,500 input tokens per call; ended in `needs_human_review` (stray number) |
| Live provider limits (headers) | 1,000 requests per day; 8,000 tokens per minute |
| Hygiene scans | em dashes, non-ASCII, AI attribution, private references: all empty (the author runs the brand term scan) |

## Open decisions raised or still open

- OD-01: confirm the queue priority weights in the YAML `queue` block (implemented as proposed). Owner: author.
- OD-09: partially closed on 2026-10-08. A valid key was provided, the smoke call succeeded and the live limits are recorded (this log and ADR-016). Still open: the acceptance run with the real LLM, moved to P1.I2b.S6. Owner: author.
- ADR-018 (Proposed): draft after the human decision, merged explain and propose, limited passages. Owner: author; accepted when implemented in Iteration 2b.
- OD-10: authentication of the approver (Phase 2); until then `actor` is self-asserted. Owner: author. ADR in Phase 2.
- OD-02 and OD-04 unchanged (Iteration 3 and 6).

## What runs today

See `docs/progress/current-state.md`.
