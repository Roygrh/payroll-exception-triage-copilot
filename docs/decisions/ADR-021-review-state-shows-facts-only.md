# ADR-021: The needs-human-review state shows facts, the policy action and the reason only

Status: Accepted
Date: 2026-10-21

Refines: ADR-009 (reconciliation paragraph). ADR-009 stays in force otherwise.

## Context

ADR-009 says that when the proposed action differs from the policy action the case goes to "needs human review" "with both actions visible and the justification shown as unvalidated". ADR-018 and AGENTS.md constraint 7 later fixed that a non-valid output must never be shown as validated and that a failed draft is not shown at all. The approver UI of Iteration 4 follows the author's approved design for this state: "a clear banner with the review reason; show the facts only, no explanation or proposal text". A case enters review for several reasons (a stray number, a unit mismatch, an unknown citation, a proposal that differs from the policy, a failed draft), and once there it stays until it is executed (ADR-018), so an explanation or proposal that validated on its own can sit next to a reason that concerns another output. The hitl-workflow-validator noted the disagreement between ADR-009 and the UI on 2026-10-21.

## Decision

- While a case is in `needs_human_review`, the case detail shows the engine facts, the timecard events of the finding's day, the policy action, the case status and the review reason. It shows no explanation, no proposal and no justification text, validated or not, and no citation buttons from them. The retrieved passages and the model call metadata stay visible, since they are not model text.
- The proposed action of a mismatch remains visible through the review reason, which names both actions (`propose: proposed action ... differs from the policy action ...`), so ADR-009's "both actions visible" still holds.
- The message step keeps ADR-018's rule: a draft that validated is shown for editing, marked as LLM generated, even on a case in review; a draft that did not validate is never shown and the body starts empty.
- The API is unchanged: it still returns the stored outputs and their status; the rule is applied by the UI.

## Consequences

- In review the approver decides from the facts; the model's text cannot steer a decision the checks did not accept.
- The full model outputs stay in the audit trail (suggestion entries) and in the API for inspection and evaluation.
- ADR-009's reconciliation paragraph is read together with this record; its index entry notes the refinement.
- Tests: `frontend/src/pages/CaseDetailPage.test.tsx` covers a review case with an invalid output and a review case whose outputs all validated.
