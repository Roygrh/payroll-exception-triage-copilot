# ADR-018: Draft the message after the human decision; merge explain and propose; limit the passages sent to the model

Status: Proposed (to be implemented and accepted in Iteration 2b)
Date: 2026-10-09

## Context

The first run with the real model (2026-10-08, `iteration-002.md`, "Showcase run") showed two problems with the Iteration 2 graph (detect, retrieve, explain, propose, draft, validate, human checkpoint, execute, audit):

1. **The draft is written for the proposed action, not for the human's action.** The draft node runs before the human checkpoint and writes the message for the policy action. When the approver chooses a different action (the run used return on an approve case), the message written for the proposal is sent unchanged. An approve needs no message at all, yet a draft is generated and paid for on every case.
2. **The token cost exceeds the free-tier budget.** Three structured calls per case used about 10,000 tokens (about 3,100 to 3,500 input tokens per call), more than the 8,000 tokens per minute of the default provider (ADR-016), so one case alone forces a retry. Most of the input is repeated across the three calls: the same system prompt, facts and retrieved passages, including passages outside the finding's own sections.

The human checkpoint, the code-owned policy (ADR-009), the "LLM never computes" rule (ADR-008) and the rule that explanation, proposal and draft always come from the LLM (AGENTS.md constraint 7) are not in question.

## Decision

- **Draft after the human decision.** The draft node moves after the human checkpoint and runs only when the human chooses return or escalate. It drafts the return message or the escalation note for the action the human chose, with the facts, the validated explanation and the human's choice as input. An approve produces no message and makes no draft call.
- **Second human step for the message.** The drafted message is validated by code (citations, stray numbers, as today) and shown to the human, who edits it and confirms before execute runs. Execute sends exactly the confirmed text; the decision audit entry keeps the chosen action, the original draft and the confirmed text. If the draft call fails or its output does not validate, the message step shows no draft and is marked `needs human review` for that output: the human writes the message or chooses another action. No template produces the message (constraint 7).
- **Explain and propose merged into one LLM call.** One structured call returns the explanation with its citations and the proposed action with its justification. Code validates each part as today (citation keys, bracketed references, stray numbers, proposal equal to the policy); a failure in either part routes the case to `needs human review`.
- **Limited passages.** Retrieval still runs and its ranked results are recorded. The passages sent to the model are limited to the finding's own sections (the sections that define the rule, as already used by the stray-number allow-list in ADR-008) and the case's deal memo. Other retrieved passages are not sent.
- **Compact serialization.** Facts, case context and passages are serialized compactly (no indentation, no repeated keys or boilerplate); the system prompt is shared and kept short.

## Consequences

- **Tokens (expected; measured in P1.I2b.S4 before and after):** an approve case makes one call instead of three; a return or escalate case makes two (merged call plus draft). With limited passages and compact input, the target is at most 5,000 tokens per MEAL_PERIOD case, so one case fits within one minute's budget of the default provider, a week ingest needs fewer retries, and the evaluation runs of Iteration 3 cost about half of what three calls per case would.
- **Correctness:** the message always matches the action the human chose; the gap found in the first run cannot occur.
- **Human checkpoint:** still unconditional before execute. For return and escalate the human acts twice (choose the action, then confirm or edit the message); for approve, once. The LLM still has no write path (ADR-009); execute runs only after the human confirms.
- **Demo flow change (demo-script steps 2 and 3):** the case detail shows the explanation, citations and proposal, but no draft. The draft appears when the approver chooses return or escalate; the approver then edits and confirms it. The narration of step 2 drops "and a draft return message"; step 3 becomes "choose Return, review the drafted message, edit, confirm". Step 4 (escalation) shows the escalation note drafted after the approver chooses escalate. `docs/requirements/demo-script.md`, `docs/architecture/overview.md` (state machine, responsibilities table, sequence diagram) and `docs/requirements/customer-workflow.md` where it describes the draft are updated when this record is accepted (P1.I2b.S3).
- **API and UI:** the decide endpoint splits into choosing the action and confirming the message for return and escalate (designed in P1.I2b.S3; the UI in Iteration 4 follows it).
- **Evaluation (ADR-003):** the harness of Iteration 3 simulates the human choosing the expected action so that drafts are produced and judged for return and escalate cases only.
- **Retrieval quality is still measured** on the full ranked results (ADR-017), even though the model sees fewer passages; a governing section missing from the finding's own sections would be a domain error caught by the domain-consistency-validator.
- **Validators:** hitl-workflow-validator PRE before the graph change and GATE after it; grounding-evaluator after the prompt change.
