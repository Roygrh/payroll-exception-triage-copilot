# ADR-007: Rule parameters YAML is the single source of truth

Status: Accepted
Date: 2026-10-07

## Context

The same numbers (meal deadline, minimum meal, penalty increments and amounts, extended-day threshold, rest minimum, eligibility deadline, overtime thresholds, occupation scales) appear in the agreement text the LLM cites, in the rule engine that computes facts, in the deal memos, and in the eval cases that define ground truth. If they drift, the gate passes against the wrong truth or the explanation cites a number the engine did not use.

## Decision

- `data/rule-parameters.yaml` holds every domain number and the Schedule A scale table, with a JSON schema (`data/rule-parameters.schema.json`) and tests that validate it.
- The agreement is rendered from a template (`corpus/templates/cgma.md.j2` or equivalent) that inserts numbers from the YAML; the rendered file is committed for readability and a test asserts that re-rendering produces the committed file.
- The rule engine loads the YAML at startup; no domain number is hard-coded in Python or TypeScript.
- Deal memos declare their relationship to scale by value; a test checks each "at scale" memo against Schedule A and that DM-04 is the only memo below scale.
- Eval cases take expected amounts and thresholds from the YAML through the same loader, not from literals.
- `docs/requirements/domain-model.md` lists the design values for human readers; the domain consistency validator checks it still matches the YAML.

## Consequences

- Changing a parameter is a one-line change plus re-rendering; the gate catches any artifact that was not regenerated.
- Phase 2's second agreement version is a second YAML (or a versioned section) rendered to a second corpus version with its own effective range.
- The template introduces a build step for the corpus; it is part of the seed command.
