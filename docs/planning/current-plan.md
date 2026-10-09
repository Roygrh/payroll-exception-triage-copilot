# Current plan (living copy; identical to initial-plan.md at bootstrap, 2026-10-07)

This file is the living plan. `initial-plan.md` is frozen. Structure: Phase > Iteration > Step. Each step has an objective, an artifact, an acceptance condition and the required validation. Validators are the subagents in `.claude/agents/`; "author" means a manual check by the author.

Conventions: step ids are `P<phase>.I<iteration>.S<step>`. Parameters always come from `data/rule-parameters.yaml` (ADR-007). Every iteration ends with the progress update procedure in `AGENTS.md`, section 5.

## Phase 0: Bootstrap

### Iteration 0: documentation and tooling (this iteration)

| Step | Objective | Artifact | Acceptance condition | Required validation |
| --- | --- | --- | --- | --- |
| P0.I0.S1 | Keep private inputs out of git | `.gitignore` with the private folder excluded | `git status` does not list the private folder once the repository is initialized | author |
| P0.I0.S2 | Portable agent rules | `AGENTS.md`, `CLAUDE.md` importing it | Hard constraints, authority hierarchy, execution loop, definition of done and progress procedure present; no duplication | author |
| P0.I0.S3 | Tool guardrails | `.claude/settings.json`, `.claude/hooks/block-git-write.sh` | `git stash list` passes, `git stash` is blocked; attribution disabled; JSON valid | hook harness (recorded in ADR-014) |
| P0.I0.S4 | Validator subagents | five files in `.claude/agents/` | Each has one responsibility, minimal tools and the PASS, FAIL, BLOCKED output format | author |
| P0.I0.S5 | Requirements | `docs/requirements/` (brief, domain model, customer workflow, demo script) | Brand-free, English, consistent with ADRs; differences from the original brief listed | author |
| P0.I0.S6 | Architecture | `docs/architecture/overview.md` | C4 context and container, state machine with needs-human-review path, responsibilities table | author |
| P0.I0.S7 | Decisions | ADR-001 to ADR-014 and index | MADR sections present; vendor facts verified and recorded (ADR-004, ADR-013, ADR-014) | author |
| P0.I0.S8 | Plan, progress, evidence | `docs/planning/`, `docs/progress/`, `docs/evidence/` | Initial and current plan identical; handoff block present; assumptions tagged | author |
| P0.I0.S9 | Hygiene scans | scan results in the iteration log | No forbidden terms, em dashes, phone numbers or compensation figures outside the private folder | author |

## Phase 1: Demo

### Iteration 1: Domain and data

| Step | Objective | Artifact | Acceptance condition | Required validation |
| --- | --- | --- | --- | --- |
| P1.I1.S1 | Project skeletons | `backend/pyproject.toml` (Python 3.12, FastAPI, pytest), `evals/`, `data/` layout, `.env.example` | `pytest` runs (zero tests is acceptable); lint configured | test-engineer |
| P1.I1.S2 | Rule parameters as single source of truth | `data/rule-parameters.yaml`, `data/rule-parameters.schema.json`, loader module, tests | Schema validation passes; tests fail when a value is removed or out of range; values equal the domain model | test-engineer, domain-consistency-validator |
| P1.I1.S3 | Agreement rendered from template | `corpus/templates/` template, `corpus/cgma-2026.1.md` rendered, render script, test | Rendered file equals re-render output; 15 to 20 pages equivalent; all sections of the outline present; every number inserted from the YAML | domain-consistency-validator, code-reviewer |
| P1.I1.S4 | Deal memos | `corpus/deal-memos/DM-01..06.yaml` (or JSON) with all fields | DM-04 below scale only; "at scale" memos equal Schedule A; DM-05 eligibility not completed | domain-consistency-validator |
| P1.I1.S5 | Seeded timecard generator | `backend/.../generator`, `data/generated/` output for the 18 scenarios, tests | Same seed produces identical output; each scenario's trigger condition holds by construction; clean weeks have no trigger | test-engineer, domain-consistency-validator |
| P1.I1.S6 | Eval case manifest | `evals/cases/manifest.yaml` with expected rule ids, sections, citation keys, action and facts per scenario | 18 entries; expectations derived from YAML and generator, not literals; negative cases included | domain-consistency-validator, code-reviewer |
| P1.I1.S7 | Iteration log and handoff | `docs/progress/iterations/iteration-001.md`, updated `current-state.md` | Procedure in AGENTS.md section 5 followed | author |

### Iteration 2: Vertical slice MEAL_PERIOD end to end

| Step | Objective | Artifact | Acceptance condition | Required validation |
| --- | --- | --- | --- | --- |
| P1.I2.S1 | Database and migrations | PostgreSQL 16 with pgvector in compose, migrations for the data model outline, checkpointer setup | `docker compose up db` plus migration command creates all tables including checkpoint tables | test-engineer |
| P1.I2.S2 | Rule engine: MEAL_PERIOD and action policy | engine module, facts schema, policy module, unit tests from YAML | SC-03, SC-04 approve with correct increments and amounts; SC-05 return; clean weeks produce no finding; policy table tested per row | test-engineer, code-reviewer |
| P1.I2.S3 | Corpus ingestion and hybrid retrieval | chunker with citation keys and version, local embeddings (ADR-017), full-text index, hybrid retrieval fused by reciprocal rank fusion, citation validator | Query for a MEAL_PERIOD finding returns section 8.2 and the deal memo chunk in the top results; citation keys resolvable to passages | grounding-evaluator (spot check), test-engineer |
| P1.I2.S4 | LLM adapter v1 | adapter interface, OpenAI-compatible implementation (default gpt-oss-20b on GroqCloud, ADR-016; OpenAI, Ollama and other endpoints by configuration), optional Anthropic implementation, client-side pacing and retry, fake adapter in a test module only, configuration from the root `.env` | Interface documented; fake adapter used in tests; real call succeeds with `uv run ptc smoke-llm` | code-reviewer |
| P1.I2.S5 | Graph: detect, retrieve, explain, propose, draft, validate, needs human review | LangGraph definition, prompts with strict JSON schemas, citation validator, stray-number check, proposal versus policy check | Run on SC-03 with the real LLM yields validated citations and a proposal equal to the policy; forced LLM failure routes to needs human review with no generated text | hitl-workflow-validator (PRE on design, POST on code), grounding-evaluator |
| P1.I2.S6 | Human checkpoint, execute, audit | interrupt before execute, resume with decision, execute node, append-only audit table | Pause, restart the API, resume with an edited message; audit shows suggestions, decision and action with actor and timestamp | hitl-workflow-validator (GATE), test-engineer |
| P1.I2.S7 | API | FastAPI endpoints: ingest week, list queue (priority order), case detail, decide (approve, return, escalate), audit by case | Demo steps 1 to 3 can be performed with API calls on the seeded week | test-engineer, code-reviewer |
| P1.I2.S8 | Iteration log and handoff | `iteration-002.md`, `current-state.md` | Procedure followed | author |

### Iteration 3: Evaluation harness and two-tier gate

| Step | Objective | Artifact | Acceptance condition | Required validation |
| --- | --- | --- | --- | --- |
| P1.I3.S1 | Harness | `evals/run.py` (or equivalent) running the graph on each manifest case with the real adapter; per-case report | One command runs all available cases and writes a JSON and a human-readable report | test-engineer, code-reviewer |
| P1.I3.S2 | Tier 1 deterministic checks | section match, passage exists for the effective version, action match, negative cases | 100% on the MEAL_PERIOD cases and clean weeks; a wrong citation key fails the case | grounding-evaluator |
| P1.I3.S3 | Tier 2 LLM judge | rubric files, judge prompt through the adapter, scores for faithfulness and completeness | Baseline run recorded; thresholds set and documented in the eval configuration and in `iteration-003.md`; calibration against hand labels recorded | grounding-evaluator |
| P1.I3.S4 | Gate command | `evals/gate` exit code, CI-friendly output | Exit non-zero when tier 1 is below 100% or tier 2 below threshold | test-engineer |
| P1.I3.S5 | Deliberately broken variant | a committed configuration or prompt variant that cites the wrong section or drops the deal memo | Gate fails on the variant with per-case reasons (demo step 5) | grounding-evaluator |
| P1.I3.S6 | Iteration log and handoff | `iteration-003.md`, `current-state.md` | Procedure followed | author |

### Iteration 4: UI

| Step | Objective | Artifact | Acceptance condition | Required validation |
| --- | --- | --- | --- | --- |
| P1.I4.S1 | Frontend skeleton | `frontend/` with React, TypeScript, Vite, API client, test runner | Builds and runs against the API | test-engineer |
| P1.I4.S2 | Prioritized queue | queue page: findings, amount, priority, status, week ending | Order equals the API's priority order; clean weeks absent | test-engineer, code-reviewer |
| P1.I4.S3 | Case detail with clickable citations | detail page: timecard events, facts, explanation with citation links opening the passage and version, deal memo citation, policy action and proposal, draft message, needs-human-review banner | Clicking a citation shows the exact passage and its citation key; the needs-human-review state shows facts only | hitl-workflow-validator, code-reviewer |
| P1.I4.S4 | Decision actions | approve, return (with editable message), escalate; resume feedback; audit panel | Demo step 3 performed in the UI; audit panel shows the three entry kinds | hitl-workflow-validator (GATE), test-engineer |
| P1.I4.S5 | Iteration log and handoff | `iteration-004.md`, `current-state.md` | Procedure followed | author |

### Iteration 5: Remaining rules and the scale conflict case

| Step | Objective | Artifact | Acceptance condition | Required validation |
| --- | --- | --- | --- | --- |
| P1.I5.S1 | EXTENDED_DAY and REST_PERIOD | engine rules, facts, premium lines, tests, prompts updated | SC-09 to SC-12 approve with correct hours and amounts; SC-02 raises nothing | test-engineer, domain-consistency-validator |
| P1.I5.S2 | TIME_ENTRY_COMPLETENESS | engine rule, tests | SC-06 to SC-08 return with the missing or out-of-order entries named | test-engineer |
| P1.I5.S3 | SCALE_RATE with dual-source citation | engine rule comparing the deal memo with Schedule A; retrieval returns both sources; escalation record | SC-13 escalates, explanation cites 5.1, Schedule A and article 3, both values shown; SC-14 escalates with the meal finding also explained (demo step 4) | grounding-evaluator, hitl-workflow-validator |
| P1.I5.S4 | ELIGIBILITY_DOC | business-day calculation, rule, tests | SC-15 and SC-16 escalate with days overdue; weekend handling tested | test-engineer, domain-consistency-validator |
| P1.I5.S5 | Multiple findings and severity | policy combination, UI listing all findings | SC-14, SC-16, SC-17, SC-18 take the most severe action; all findings explained | grounding-evaluator |
| P1.I5.S6 | Gate on the full suite | manifest complete, thresholds re-checked | Tier 1 at 100% on 18 cases; tier 2 above thresholds | grounding-evaluator (GATE) |
| P1.I5.S7 | Iteration log and handoff | `iteration-005.md`, `current-state.md` | Procedure followed | author |

### Iteration 6: Tracing, one-command compose with seed, demo rehearsal

| Step | Objective | Artifact | Acceptance condition | Required validation |
| --- | --- | --- | --- | --- |
| P1.I6.S1 | Tracing | OpenTelemetry spans per node and LLM call, exporter to Langfuse Cloud US, `.env.example` entries | Traces for one case visible in the tracing UI with case id, rule ids, model and adapter version; exporter fails open when unreachable | code-reviewer |
| P1.I6.S2 | One-command start with seed | `deployment/docker-compose.yml`, seed service, `make demo` or equivalent | Cold start to a filled queue with one command on a clean machine; reset command documented | test-engineer |
| P1.I6.S3 | Demo rehearsal | rehearsal notes in `iteration-006.md`, fixed timings | Steps 1 to 5 under 10 minutes twice in a row; fallback for provider outage rehearsed | author, hitl-workflow-validator (GATE), grounding-evaluator (GATE) |
| P1.I6.S4 | Phase 1 closure | README updated with run instructions and the success criterion statement; `current-state.md` marks Phase 1 done | All Phase 1 steps done per definition of done | author |

## Phase 2: Portfolio (outline)

| Iteration | Scope | Decisions needed |
| --- | --- | --- |
| P2.I7 | Multi-provider gateway behind the adapter: second provider, optional local model, fallback, cost and latency controls | ADR for provider selection and fallback policy |
| P2.I8 | Second agreement version with effective dates; effective-date filter in retrieval; versioned eval expectations; citation fidelity as a formal metric | ADR for corpus versioning scheme |
| P2.I9 | Permission-filtered retrieval by role and department (ADR-011); role model and demo users | ADR for the permission model |
| P2.I10 | Function 4 Rules Q&A with citations, refusal with route to a specialist; ambiguous-case classifier with confidence score | ADR for refusal policy and confidence thresholds |
| P2.I11 | Expanded eval suite on a dedicated LLM evaluation framework; regression history | ADR for framework choice |
| P2.I12 | Audit viewer and metrics dashboard | none expected |
| P2.I13 | Self-hosted tracing (ADR-004 Phase 2) and serverless deployment on the primary cloud provider with infrastructure as code | ADR for deployment topology |
| P2.I14 | Discovery kit: questions derived from the unknowns in ADR-001, metrics to measure in a pilot | none expected |

## Plan changes

- 2026-10-08 (Iteration 1): no step contract changed. Author decisions applied: ADR-015 (uv) adds `uv.lock` and `.python-version` to the P1.I1.S1 artifacts; OD-03 resolved (hook tests at `.claude/hooks/tests/run.sh`, ADR-014); OD-05 resolved (four filler crew in P1.I1.S5). Added to P1.I2.S2 as a prerequisite from the Iteration 1 code review: move the timecard model and the policy table into shared modules (`payroll_triage/timecards.py`, `payroll_triage/policy.py`) before building the MEAL_PERIOD rule, and test the engine against the committed manifest.

- 2026-10-08 (Iteration 2): author decisions applied before the build: OD-06 closed (article 2 text stands), OD-07 closed (penalty schedule 8.25 / 11.00 / 13.75 kept), OD-08 closed (guild local number removed everywhere, data regenerated, `ptc check` green). ADR-016 (default LLM gpt-oss-20b on GroqCloud through an OpenAI-compatible adapter, other endpoints and Anthropic by configuration, single root `.env`, pacing and retry) supersedes ADR-002 on the provider choice; P1.I2.S4 edited accordingly. ADR-017 (local embeddings, hybrid retrieval with reciprocal rank fusion); P1.I2.S3 edited accordingly. P1.I2.S5 acceptance now names the real LLM and the stray-number check (ADR-008). The queue priority weights moved into a `queue` block of `data/rule-parameters.yaml` (ADR-007) with the formula implemented in P1.I2.S2 instead of S7; OD-01 stays open for the author's confirmation of the weights. Carried-forward work done at the start of P1.I2.S2: shared `timecards.py` and `policy.py` with a test per ADR-009 row, and the no-meal-day exception (agreement 7.4 and 8.7) in the engine and the oracle. Architecture documentation now includes a C4 level 3 component diagram and a sequence diagram of the human checkpoint (P1.I2.S5 and S6 artifacts). Deviation: the hitl-workflow-validator PRE run on the design was not performed as a separate step before coding; the POST run on code and the GATE run cover the same checks and are recorded in `iteration-002.md`.
