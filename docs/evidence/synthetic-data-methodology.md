# Synthetic data methodology

How the agreement, deal memos, crew and timecards are produced so that they are realistic in structure, free of real text and names, reproducible, and consistent with the rule parameters (ADR-001, ADR-006, ADR-007).

## 1. Principles

1. **Structure is realistic, content is invented.** The agreement imitates how such documents are organized (numbered articles, definitions, schedules) but every sentence is written for this project. No passage is copied or paraphrased from a real collective agreement.
2. **One source of numbers.** Every domain value comes from `data/rule-parameters.yaml`. The agreement template, the deal memos, the generator and the eval manifest read it; nothing retypes a number.
3. **Scenario-driven.** Timecards are generated to satisfy the scenario catalog in `docs/requirements/domain-model.md` (18 scenarios), not sampled randomly and then labeled. Each scenario states its trigger condition; the generator constructs events that meet it with a margin (for example a meal at 6.5 hours, not 6.01).
4. **Seeded and reproducible.** The generator takes a seed; the same seed yields byte-identical output. The seed used for the committed demo data is recorded in the data folder.
5. **No personal data.** Employee names are invented per deal memo and per filler entry and recorded only in `corpus/deal-memos` and `data/scenarios.yaml`; they match no person in the source material. No emails, phone numbers, addresses or identifiers that look real.
6. **No real organizations.** Production, employer and guild names are invented; no guild local number is used (OD-08, Iteration 2). The domain consistency validator and the author's term scan check this.

## 2. The agreement (CGMA 2026.1)

- Template with placeholders for every parameter and for the Schedule A and Schedule B tables; rendered to `corpus/cgma-2026.1.md`.
- Length target 15 to 20 pages equivalent (roughly 6,000 to 9,000 words) so retrieval has realistic distractors: definitions, allowances, holidays, grievances and corrections articles exist even though no Phase 1 rule cites them.
- Each section carries a stable anchor so citation keys (`CGMA-2026.1-8.2`) resolve to one passage; chunking follows section boundaries.
- Jurisdiction (hire state versus work state) is described in article 2 in general terms; no state-specific rule is encoded in Phase 1.
- A second version (Phase 2) is produced by rendering a second parameter set with a different effective range and at least one changed value, so the effective-date filter has an observable effect.

## 3. Deal memos

- Six memos (DM-01 to DM-06) with the fields in the domain model.
- Relationship to scale is a design choice per memo: above, at, below. A test asserts DM-04 is the only memo below scale and that "at scale" memos equal Schedule A exactly.
- Start dates and eligibility completion dates are chosen relative to the demo week so that only DM-05 is overdue on the demo date.

## 4. Timecards

- Each scenario is one timecard for one deal memo employee on one week ending; the scenarios of an employee are spread over consecutive week endings counting back from the demo week 2026-03-14 (see the domain model, section 7). Four filler crew with generated at-scale deal memos have clean timecards on the demo week.
- Per day: date, day type, work location, call, meal out, meal in, wrap in decimal hours from midnight of the shift date, in tenths of an hour (values above 24.0 for next-day wraps). Monday to Friday are work days; Saturday and Sunday are omitted.
- Scenario construction rules:
  - Clean day: call 7.0, meal 12.0 to 12.5, wrap 15.5 (8.0 hours worked).
  - Late meal: meal out at call plus deadline plus the scenario's lateness (0.5 h, 0.8 h or 1.2 h), meal duration 0.5 h, day length under 12 hours.
  - Short meal: meal duration 24 minutes (0.4 h), otherwise clean.
  - Missing punch: the named field is null; other days clean.
  - Wrap before call: wrap value lower than call on one day.
  - Extended day: hours worked 13.5 or 12.5 with a compliant meal before 6.0 hours.
  - Rest invasion: wrap on day N and call on day N plus 1 such that rest is 8.5 h or 9.5 h; one case crosses midnight.
  - Below scale and eligibility scenarios: clean punches; the finding comes from the deal memo.
  - Multiple findings: compose two of the above on different days of the same week.
- Every generated week is checked by construction tests: the engine's findings on the generated data equal the scenario's expected rules.

## 5. Eval manifest

- One entry per scenario with expected rule ids, sections, citation keys, policy action, and the engine facts (so tier 1 of the gate compares structured values).
- The manifest is generated alongside the data, from the same seed and parameters, and committed.
- Quality rubrics for tier 2 are written by hand in Iteration 3 and stored in `evals/rubrics/`.

## 6. What is intentionally not synthetic

- The eligibility deadline (3 business days) mirrors the public government rule (S-05 in `sources.md`).
- The United States is the implied jurisdiction (hire state, work state, USD); no state law is encoded.

## 7. Validation

- `domain-consistency-validator` after any change to the YAML, the template, the deal memos, the generator or the manifest.
- The author's forbidden-term scan before each commit.
- A test that re-renders the agreement and compares it with the committed file.
