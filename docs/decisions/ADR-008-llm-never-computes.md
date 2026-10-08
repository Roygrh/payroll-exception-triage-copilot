# ADR-008: The LLM never computes

Status: Accepted
Date: 2026-10-07

## Context

Payroll is audited. A number in an explanation ("the meal began 6.5 hours after call, two penalty increments, 17.50 USD") must be exactly the number the pay engine used. Language models are unreliable at arithmetic and at time arithmetic in particular (decimal hours, wraps past midnight, business days). Letting the model derive numbers would also make the evaluation gate measure arithmetic instead of explanation quality.

## Decision

- The rule engine computes every fact: hours to meal, meal duration, minutes late, penalty increments, amounts, hours worked, hours over threshold, rest hours, invaded hours, days overdue, scale shortfall. Facts are passed to the LLM as structured input (a typed JSON object per finding) together with the retrieved passages.
- Prompts instruct the model to use only the provided facts and to cite them by name; prompts never ask the model to calculate, convert, round or count.
- The citation validator and the tier 2 judge (ADR-003) check that no number appears in the explanation or the draft that is not present in the facts or the cited passage. A stray number is a faithfulness failure.
- The deterministic pay lines added on approve come from the engine, never from text produced by the model.

## Consequences

- Facts schemas are part of the engine's public contract and are versioned with the eval cases.
- Explanations remain grounded even when a model is swapped (ADR-002), because the numbers never depended on the model.
- The model's job is narrower and easier to evaluate: map facts and passages to clear language, propose and justify, and draft.
