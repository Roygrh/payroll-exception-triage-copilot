# ADR-001: Evidence profile E3, grounded synthetic problem with synthetic data

Status: Accepted
Date: 2026-10-07

## Context

The project is a demo and portfolio piece built without access to a customer. The author's research consists of public product documentation of entertainment payroll vendors (onboarding and timekeeping modules) and the description of the target role. There is no measured data about exception volumes, time per exception or error rates. The project needs to be honest about what is known, what is inferred and what is invented, both for the author's own discovery conversations and for anyone reading the repository.

## Decision

Adopt evidence profile E3: grounded synthetic problem, synthetic data.

- **Grounded:** the workflow, the timecard fields, the approval statuses, the offer fields, the role of the deal memo and the existence of document compliance tracking are taken from public product documentation of vendors in this category (described generically, ADR-006). The product mirrors that vocabulary.
- **Hypothesis:** that human exception queues are the main operational pain is a hypothesis derived from the feature set (rejection states, personal queues, bulk approvals, correction loops). It is to be validated in discovery, not asserted as fact.
- **Unknown:** volumes of exceptions per week, minutes per exception, share of each exception type, and cost of a late payroll run. No number in the repository claims to measure them.
- **Synthetic:** the agreement, the rates, the penalty table, the productions, the crew and the timecards are invented. One parameter is intentionally real: the employment eligibility verification deadline of 3 business days after the start date, taken from the public government source, because the scenario needs a real-world deadline to be credible. It is recorded as such in `docs/evidence/sources.md`.

## Consequences

- `docs/evidence/profile.md` states the profile; `docs/evidence/assumptions.md` tags every assumption with its origin (from brief, from approved decision, introduced in bootstrap).
- Demo narration and README must not claim measured impact. Phrases such as "saves N hours" are forbidden until measured.
- Discovery questions for a real customer are a Phase 2 deliverable derived from the unknowns list.
- The synthetic data methodology (`docs/evidence/synthetic-data-methodology.md`) is the contract for generated data: seeded, scenario-driven, parameterized from the YAML, and free of real names and text.
