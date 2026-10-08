# ADR-005: Vertical slice first, MEAL_PERIOD end to end

Status: Accepted
Date: 2026-10-07

## Context

Six rules, a graph with a human checkpoint, retrieval, three LLM functions, an eval gate and a UI compete for a two-week window. Building layer by layer (all rules, then the graph, then the UI) risks reaching the demo date with no end-to-end path. The demo's first three steps all run on a single case.

## Decision

Iteration 2 delivers one rule, MEAL_PERIOD, through the entire path: detect, retrieve, explain, propose, draft, validate citations, human checkpoint, resume, execute, audit, exposed via the API and covered by tests, with the real LLM adapter. Only after that slice works are the remaining rules (Iteration 5), the gate (Iteration 3) and the UI (Iteration 4) added.

MEAL_PERIOD was chosen because it exercises both approve (late meal with complete data) and return (meal under 30 minutes), it needs a premium calculation (penalty increments and amounts), and it is the example in the brief's pitch.

## Consequences

- The data model, graph state, adapter interface and audit schema are designed for all six rules in Iteration 1, but only MEAL_PERIOD is wired in Iteration 2.
- The eval harness (Iteration 3) starts with the MEAL_PERIOD cases and the two clean weeks; the other cases are added with their rules in Iteration 5.
- Demo steps 1 to 3 can be rehearsed on the slice before the UI exists (via API calls), which de-risks the schedule.
- Widening must not refactor the slice's contracts; if it does, the change needs an ADR.
