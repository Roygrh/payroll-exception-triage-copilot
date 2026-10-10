# Roadmap

A one-page view of the plan for day-to-day use. It takes no decisions: the contract for every step (objective, artifact, acceptance condition, validation) is in [`current-plan.md`](current-plan.md), and where the two differ, the plan wins.

Execution order of Phase 1 (from 2026-10-09): **2b, 4, 3, 5, 6**. The UI comes before the evaluations so that a demo can be recorded early; the demo will be shown as a recorded video and in a live online session. Status as of 2026-10-09.

All `ptc` commands run from `backend/` with uv; the database must be up (`docker compose -f deployment/docker-compose.yml up -d db` from the repository root) and the free provider key must be in the root `.env`.

## Phase 0: Bootstrap

### [Iteration 0: documentation and tooling](current-plan.md#iteration-0-documentation-and-tooling-this-iteration): done

- **Goal:** set the rules, decisions and agent tooling before any code.
- **Delivers:** AGENTS.md, requirements, architecture, ADR-001 to ADR-014, the git guard hook, five validator agents.
- **Demo value:** none on screen; the documentation shows how the project is governed.
- **Verify:** `bash .claude/hooks/tests/run.sh` (86 cases pass); read `docs/progress/iterations/iteration-000.md`.

## Phase 1: Demo

### [Iteration 1: domain and data](current-plan.md#iteration-1-domain-and-data): done

- **Goal:** a synthetic agreement, deal memos and timecards that the whole demo runs on.
- **Delivers:** rule parameters YAML, the rendered agreement, deal memos, a seeded generator (22 timecards) and the 18-case expectation manifest.
- **Demo value:** the agreement and the data can be opened and read; every number traces back to one YAML file.
- **Verify:** `uv run ptc check` (green means agreement, data and manifest equal their regeneration).

### [Iteration 2: MEAL_PERIOD end to end](current-plan.md#iteration-2-vertical-slice-meal_period-end-to-end): built, acceptance moved to 2b

- **Goal:** one rule running through the whole pipeline: detect, retrieve, LLM explanation and proposal, validation, human checkpoint, execute, audit.
- **Delivers:** database, rule engine, hybrid retrieval, LLM adapter, LangGraph graph, API.
- **Demo value:** demo steps 1 to 3 over the API and the console showcase.
- **Verify:** `uv run pytest` (175 tests); `uv run ptc smoke-llm` (done 2026-10-08); `uv run ptc serve` and open `http://127.0.0.1:8000/docs`.

### [Iteration 2b: fixes from the first real run and token efficiency](current-plan.md#iteration-2b-fixes-from-the-first-real-run-and-token-efficiency): next

- **Goal:** make the real model pass the slice cleanly and cheaply.
- **Delivers:** `hours_late` as an engine fact, rejection of bracketed pseudo-references, the message drafted after the human's decision (ADR-018), one merged explain-and-propose call with fewer passages, the audit field fix.
- **Demo value:** a clean SC-03 approval and an SC-05 return with a correction message written for the return; at most half the tokens per case of the first run.
- **Verify:** `uv run pytest`; `uv run ptc check`; `uv run ptc showcase --decision approve` (ends approved, no `needs_human_review`); `uv run ptc showcase --scenario SC-05 --decision return` (the message speaks about a return); tokens per case printed and at most 5,000.

### [Iteration 4: UI](current-plan.md#iteration-4-ui): pending (after 2b)

- **Goal:** the approver works the queue in a browser.
- **Delivers:** queue page, case detail with clickable citations, decision buttons, message editing, audit panel.
- **Demo value:** demo steps 1 to 3 on screen; enough to record the first video.
- **Verify:** start the API and the frontend (commands recorded in `iteration-004.md`); ingest the week, open the top case, click a citation (the passage at section 8.2 opens), choose Return, edit and confirm the message, see the audit panel.

### [Iteration 3: evaluation harness and two-tier gate](current-plan.md#iteration-3-evaluation-harness-and-two-tier-gate): pending (after 4)

- **Goal:** measure the model against known answers before any version ships.
- **Delivers:** a harness over the manifest, deterministic checks, an LLM judge, a gate command and a deliberately broken variant.
- **Demo value:** demo step 5: the gate passes, then fails on the broken variant with per-case reasons.
- **Verify:** the eval and gate commands (named in `iteration-003.md`); the report shows tier 1 at 100% on the MEAL_PERIOD cases; the broken variant exits non-zero. Runs are paced by the free-tier limits.

### [Iteration 5: remaining rules and the scale conflict case](current-plan.md#iteration-5-remaining-rules-and-the-scale-conflict-case): pending (after 3)

- **Goal:** all six rules, including the deal memo versus agreement conflict.
- **Delivers:** EXTENDED_DAY, REST_PERIOD, TIME_ENTRY_COMPLETENESS, SCALE_RATE, ELIGIBILITY_DOC, multiple findings per case, the gate on all 18 cases.
- **Demo value:** demo step 4: SC-13 shows both sources and escalates.
- **Verify:** ingest the week and see every scenario in the queue; open SC-13 in the UI; the gate passes on the full suite.

### [Iteration 6: one command, tracing, rehearsal](current-plan.md#iteration-6-tracing-one-command-compose-with-seed-demo-rehearsal): pending (last)

- **Goal:** a stranger can start the demo with one command, and the demo is rehearsed.
- **Delivers:** tracing per node and LLM call, one-command start with seed, rehearsal notes, README run instructions.
- **Demo value:** the full 10-minute demo, the final video and the live session.
- **Verify:** on a clean machine, the one command fills the queue; steps 1 to 5 run under 10 minutes twice; one case's trace is visible in the tracing tool.

## [Phase 2: Portfolio](current-plan.md#phase-2-portfolio-outline): pending

- **Goal:** extend the demo into a portfolio piece: more providers (including a local model through Ollama), agreement versions, permissions, rules Q&A, richer evaluations, dashboards, deployment.
- **Demo value:** decided per iteration (P2.I7 to P2.I14 in the plan).
- **Verify:** defined when each iteration is planned.
