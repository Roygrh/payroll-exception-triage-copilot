# ADR-009: Action policy owned by code

Status: Accepted
Date: 2026-10-07

## Context

The brief's Resolution Proposer has the LLM propose approve, return or escalate. An auditor will ask why a case was approved; "the model said so" is not an acceptable answer, and a model that sometimes proposes a different action for the same facts cannot be the basis of a consistent queue. At the same time, constraint 7 requires that the resolution proposal remains an LLM output, not a template.

## Decision

Code owns the action policy; the LLM produces the proposal and its justification, and the two are reconciled.

Policy (evaluated per finding, then combined):

| Situation | Policy action |
| --- | --- |
| Premium pay finding (late meal, extended day, rest invasion) with complete, plausible data | approve: code adds the premium line |
| Incomplete or implausible data (missing or out-of-order punches, meal under the minimum, implausible day length) | return |
| Compliance block (eligibility overdue) or source conflict (deal memo below scale) | escalate |

Combination: several findings on one timecard produce the most severe action, with the order escalate > return > approve.

Reconciliation: the propose node receives the findings, the facts, the retrieved passages and the policy action. The LLM returns a proposed action, a justification and, for returns, the specific correction requested. The validator compares the proposed action with the policy action. Equal: the case proceeds to the human checkpoint with the proposal shown. Different: the case is routed to "needs human review" with both actions visible and the justification shown as unvalidated. Code never overwrites the proposal silently, and the proposal never changes the policy action.

Execution: only the human's decision is executed, under the human's identity, by code. The LLM has no write path.

## Consequences

- Eval tier 1 checks "proposed action equals expected action" (ADR-003), which also checks the policy implementation.
- The UI shows the policy action and the proposal; in the normal case they are the same and the user sees one recommendation with a justification.
- The policy table lives in code with tests per row and is cited in the explanation prompts so the justification can refer to it.
- Future policy changes (for example, approving short meals when the department head confirms) are code changes with an ADR, not prompt changes.
