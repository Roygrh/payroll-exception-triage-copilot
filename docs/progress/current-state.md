# Current state

## Handoff

**Done**
- Iteration 000 (2026-10-07): bootstrap. Rules, tool guardrails (git guard hook), five validator subagents, requirements, architecture, ADR-001 to ADR-014, plan, evidence set.
- Iteration 001 (2026-10-07 to 2026-10-08): domain and data. Rule parameters YAML with schema and semantic validation (ADR-007); Crew Guild Master Agreement 2026.1 rendered from a template (about 6,500 words, 97 anchored sections); six deal memos checked against Schedule A; scenario catalog and seeded generator (22 timecards: 18 scenarios plus 4 filler); expectation oracle and evaluation manifest (18 cases); ADR-015 (uv); hook test suite moved into the repository. 102 backend tests, 86 hook cases, all validators PASS at the gate (see `iterations/iteration-001.md`).

**Next**
- The author: review and commit Iteration 1; decide OD-07 (penalty schedule 8.25 / 11.00 / 13.75 versus the brief's values, see iteration-001 deviation 1).
- Then step **P1.I2.S1** (database and migrations: PostgreSQL 16 with pgvector in compose, data model outline, checkpointer setup). Validator: test-engineer. Before P1.I2.S2, do the carried-forward refactor: shared timecard model module and `policy.py` with a test per ADR-009 row, then build the MEAL_PERIOD rule on `calc.py` and test it against the committed manifest.

**Open decisions**
- OD-01: Queue priority formula (domain model, section 3, proposed). Owner: author. Decide in P1.I2.S7.
- OD-02: Tier 2 thresholds and judge model (ADR-003). Owner: author. Decide in P1.I3.S3 after the baseline run.
- OD-04: LangGraph instrumentation library for OpenTelemetry (ADR-004). Owner: author. Decide in P1.I6.S1.
- OD-06: Exact agreement wording for article 2 (jurisdiction). Owner: author. Current text (2.2, more favorable provision applies when hire state and work state differ) stands unless changed; no Phase 1 rule depends on it.
- OD-07: Confirm or revert the synthetic penalty schedule. Owner: author. Decide before Iteration 2 prompts.
- OD-08: Keep or change "Local 11" and the employer association name (cosmetic). Owner: author.
- Closed in Iteration 1: OD-03 (hook tests at `.claude/hooks/tests/run.sh`), OD-05 (four filler crew).

## Phase and iteration

Phase 1. Iteration 1 complete. Iteration 2 (vertical slice MEAL_PERIOD end to end) not started.

## What runs today

From `backend/` (uv required, ADR-015):

```
uv sync
uv run pytest                    # 102 tests
uv run ruff check .
uv run ptc check                 # committed agreement, generated data and manifest equal regeneration
uv run ptc render-agreement      # regenerate corpus/cgma-2026.1.md
uv run ptc generate-data         # regenerate data/generated/
uv run ptc build-manifest        # regenerate evals/cases/manifest.yaml
```

From the repository root:

```
bash .claude/hooks/tests/run.sh  # 86 git guard cases
```

## Known gaps

- No database, API, graph, LLM adapter or UI yet (Iteration 2 onward).
- `Timecard` and `TimecardDay` live in the generator module and the policy decision is inlined in the expectation oracle; both move to shared modules at the start of Iteration 2 (carried-forward review finding).
- Deal memos are YAML only; the retrieval corpus for deal memos (chunks with citation keys) is built in P1.I2.S3.
- Custom validator agents were not registered in the bootstrap session; they were run as general-purpose agents loading the definitions. New sessions can invoke them directly.

## Risks

- Schedule: five iterations remain for the two-week target; the vertical slice (ADR-005) is the mitigation.
- The penalty schedule decision (OD-07) touches the agreement text, data and manifest; deciding it late means regenerating prompts and eval baselines.
- LLM judge calibration (ADR-003) may need more hand-labeled cases than planned.
