# Iteration 001: Domain and data

Dates: 2026-10-07 to 2026-10-08
Phase: 1
Scope: Phase 1, Iteration 1 as defined in `docs/planning/current-plan.md` (steps P1.I1.S1 to S7). No LLM calls, no graph, no API, no UI.

## Summary

The domain now exists as data and code with one source of numbers. `data/rule-parameters.yaml` is validated by a JSON schema and semantic checks; the Crew Guild Master Agreement (version 2026.1, about 6,500 words, 97 anchored sections) is rendered from a template that takes every domain number from the YAML; six deal memos are authored and checked against Schedule A; a seeded generator builds 22 timecards (18 scenarios plus 4 filler crew) whose trigger conditions hold by construction; and the evaluation manifest records 18 cases (16 positive, 2 negative) with expected rules, sections, citation keys, policy action and engine facts. Everything is reproducible with `uv run ptc check`. The backend suite has 102 tests; the git guard hook suite (86 cases) moved into the repository.

## Author decisions recorded at the start of the iteration

- ADR-009 refinement accepted: the LLM proposes the action; a mismatch with the code-owned policy routes the case to human review (status line of ADR-009 updated).
- ADR-015 (new): Python dependency management with uv, Python 3.12, lockfile committed, plus the Iteration 1 dependency set.
- Open decision OD-03 closed: the hook test cases live at `.claude/hooks/tests/run.sh`, one-line command documented in ADR-014.
- Open decision OD-05 closed: four filler crew with clean timecards on the demo week, listed in the scenario catalog as SC-F01 to SC-F04.

## Steps completed

| Step | Artifact | Acceptance evidence | Validators |
| --- | --- | --- | --- |
| P1.I1.S1 | `backend/pyproject.toml`, `backend/uv.lock`, `backend/.python-version`, `backend/src/payroll_triage/`, `.env.example`, `data/README.md`, `evals/README.md` | `uv sync` resolved Python 3.12.7; `uv run pytest` ran; ruff configured | test-engineer PASS (S1 and S2 run) |
| P1.I1.S2 | `data/rule-parameters.yaml`, `data/rule-parameters.schema.json`, `params.py`, `tests/test_params.py` | Schema validation passes; 7 missing-value and 10 out-of-range cases rejected; semantic checks (citation prefix, duplicate codes, time-unit multiples); values equal the domain model | test-engineer PASS; domain-consistency-validator PASS (2 minors, fixed: plausibility and time-unit rows added to the domain model table; 3.2 added to the outline) |
| P1.I1.S3 | `corpus/templates/cgma.md.j2`, `corpus/cgma-2026.1.md`, `corpus/render.py`, `cli.py`, `tests/test_render.py` | Committed render equals re-render (`ptc check`); 6,537 words by `wc -w` (15 to 20 pages equivalent); every outline section present with its citation key; every domain number asserted against the YAML; changing a parameter changes the text | domain-consistency-validator FAIL then fixed (see Deviations, penalty schedule); code-reviewer FAIL then fixed (a literal em dash produced by the formatter in a test; minors: import masking in `ptc check`, lossless hours formatting, templated cross-references, extra tests, CLI error handling, ordinals) |
| P1.I1.S4 | `corpus/deal-memos/DM-01..06.yaml`, `corpus/deal_memos.py`, `tests/test_deal_memos.py` | DM-04 is the only memo below scale; at-scale memos equal Schedule A exactly; DM-05 verification pending; DM-04 hire state differs from work state; round trip and consistency checks | domain-consistency-validator PASS (minor: DM-04 comment retyped a scale value, fixed) |
| P1.I1.S5 | `data/scenarios.yaml`, `data/scenarios.py`, `data/generator.py`, `calc.py`, `evals/expectations.py`, `data/generated/timecards.json`, `data/generated/filler-deal-memos.json`, tests | Same seed yields identical output and scenario timecards do not depend on the seed; each of the 18 scenarios yields exactly its expected rules and combined action by construction; clean weeks and filler yield nothing; one timecard per employee per week; times in tenths | test-engineer PASS; domain-consistency-validator PASS (minors: filler ids wording and counts partition, fixed); code-reviewer PASS (minors applied, see below) |
| P1.I1.S6 | `evals/manifest.py`, `evals/cases/manifest.yaml`, `tests/test_manifest.py` | 18 cases, 16 positive, 2 negative; expectations equal the catalog; every citation key resolves to a heading of the rendered agreement; version in force for every week ending; facts follow the parameters (increments, amounts, premiums, deadline and overdue days) | code-reviewer PASS; domain-consistency-validator (gate run, below) |
| P1.I1.S7 | this file, `current-state.md`, `current-plan.md` (plan changes entry) | Procedure in AGENTS.md section 5 | author |

## Iteration gate

Run on the final state of the iteration (2026-10-08), three validators in parallel:

| Validator | Status | Summary |
| --- | --- | --- |
| test-engineer | PASS | 99 tests at gate time (102 after the last guard tests were added), 0 skipped; ruff check and format clean; `ptc check` exit 0; hook suite 86 passed |
| code-reviewer | PASS | All seven post-review fix groups verified correct with no regressions; minors applied after the gate: guard tests for `_ordinal`, `_check_unit`, the Monday start-date guard and the filler jitter guards; catalog key validation in `parse_catalog`; jitter validated once per catalog in `generate`; simpler CLI error test; a true half-up rounding case; manifest fixture passes memos explicitly |
| domain-consistency-validator | PASS | Every number, section, citation key, scenario, expected rule, action and count agrees across YAML, agreement, deal memos, scenarios, generated data, manifest and the domain model; agreement prose original; no brands, no em dashes. Minors applied after the gate: ADR-008 example corrected to 6.8 h; plausibility documented for REST_PERIOD too; stale wording removed; methodology sentence on names reworded; recording unit pinned in the schema |

After the post-gate minors: 102 tests pass, `ptc check` exit 0, hook suite 86 passed, hygiene scans empty. Validators ran as general-purpose agents loading the definitions in `.claude/agents/` (see Deviations, item 6).

## Deviations from the plan and from the brief

1. **Penalty schedule changed from 7.50 / 10.00 / 12.50 to 8.25 / 11.00 / 13.75.** The S3 domain validator reported that the brief's three amounts, with 30-minute increments, reproduce a widely published real meal penalty table, which conflicts with hard constraint 6 (no copied agreement content) and with ADR-001 (all parameters fictitious except the eligibility deadline). Because the YAML is the single source of truth, the change was one line plus re-rendering; the domain model, ADR-008's illustrative amount and the tests were updated. **The author should confirm this change or revert it** (one line in `data/rule-parameters.yaml`, then `uv run ptc render-agreement`, `generate-data`, `build-manifest`). The deadline (6.0 h), minimum meal (30 min) and rest minimum (10.0 h) are common industry norms rather than distinctive text and were left as the brief specified.
2. **Timecard times in tenths of an hour.** Recorded in the YAML (`payroll.time_unit_hours`) and the domain model. Consequences: SC-04 uses 7.2 h (brief: 7.25), SC-05 a 24-minute meal (brief: 20), SC-14 6.8 h (brief: 6.75). The parameters loader rejects hour-valued parameters that are not multiples of the unit, and the generator rejects scenario inputs that are not.
3. **DM-05 start date moved from 2026-03-09 to 2026-03-02** so the employee has two payroll weeks (SC-15 and SC-16). Deadline 2026-03-05; 7 business days overdue on the demo date.
4. **Scenarios spread across week endings** (2026-02-14 to 2026-03-14) so no employee has two timecards in one week; showcase scenarios and filler are on the demo week. Recorded in the domain model, section 7.
5. **Expectation oracle built in Iteration 1.** `evals/expectations.py` derives expected findings and facts by construction from the generated timecards using `calc.py`, so the manifest carries engine facts as the domain model requires. The Iteration 2 engine reuses `calc.py` and is tested against the committed manifest, not the reverse.
6. **Validators ran as general-purpose agents** that load the definitions in `.claude/agents/`, because the custom agent types were created after this session started and were not registered in it. Future sessions can invoke them directly.
7. Scenario categories: SC-14 is categorized `scale_rate` and SC-16 `eligibility` (their escalating rule), matching the brief's counts line (rate below scale 2, eligibility overdue 2, multiple findings 2).

## Validator findings carried forward

- **Refactor before the engine (code-reviewer, minor):** move `Timecard` and `TimecardDay` out of the generator into a neutral domain module, and move the action constants, `SEVERITY` and the per-row policy decision into `payroll_triage/policy.py` with a test per row (ADR-009 "policy table in code"). Planned for P1.I2.S2 so the engine and the oracle share one policy implementation.
- **Tier 1 should read the committed manifest** (`load_manifest()`), not rebuild it, so a policy change cannot re-baseline silently (P1.I3.S2).
- **No-meal day exception (domain validator, minor):** agreement 7.4 and 8.7 say a work day dismissed before the meal deadline records meal out = meal in = wrap and is neither incomplete nor penalized; the oracle would treat it as a short meal. No scenario exercises it. The Iteration 2 engine and the oracle must implement the exception together (or the sentence is dropped from the agreement) before P1.I2.S2 closes.
- **Recording unit pinned:** `payroll.time_unit_hours` is a fixed convention (tenths) assumed by `calc.py`; the schema now pins it with `const`.
- **Premium line semantics** recorded in the domain model (full pay at the multiplied rate replaces base pay for those hours); the Iteration 2 pay summary must honor it.
- **Ordinal table** covers 1 to 10 (the schema's maximum schedule length) and raises beyond.
- `pytest` `addopts = "-q"` makes `-q -rA` print only dots; drop `-q` if the summary line is wanted on the command line (optional).

## Metrics

| Metric | Value |
| --- | --- |
| Backend tests | 102 passed, 0 skipped (9 files) |
| Hook guard tests | 86 passed |
| Agreement | 6,537 words (`wc -w`), 97 anchored headings, 20 outline sections asserted |
| Timecards generated | 22 (18 scenarios, 4 filler) |
| Eval cases | 18 (16 positive, 2 negative) |
| Lint | ruff clean, format clean |
| Hygiene scans | forbidden terms, em dashes, private references, attribution, tool names: all empty |

## Open decisions raised

- OD-07: Confirm or revert the synthetic penalty schedule (deviation 1). Owner: author. Decide before Iteration 2 prompts are written.
- OD-08: "Local 11" and the employer association name follow real naming patterns without naming a real body; keep, or pick a less common local number. Owner: author. Cosmetic.

## What runs today

```
cd backend
uv sync
uv run pytest
uv run ruff check .
uv run ptc check                 # committed agreement, data and manifest equal regeneration
uv run ptc render-agreement      # after editing the template or the YAML
uv run ptc generate-data         # after editing scenarios.yaml, the YAML or the deal memos
uv run ptc build-manifest        # after any of the above
bash ../.claude/hooks/tests/run.sh   # from the repository root: bash .claude/hooks/tests/run.sh
```
