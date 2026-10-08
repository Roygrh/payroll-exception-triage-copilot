# Demo script (10 minutes)

This script governs Phase 1 scope: if a component does not appear here, it is not built in Phase 1. Each step lists what must exist for it to run and which iteration delivers it.

Setting: one command starts the stack with seeded data (Iteration 6). The persona is the production accountant working the queue one business day before the payroll run (see `customer-workflow.md`, section 8).

## Step 1 (about 1.5 min): ingest and detect

Narrative: "A week of timecards for the production comes in. The rule engine detects findings and fills the prioritized queue."

- Action: trigger ingestion of the seeded week (API call or button). The queue shows the exception cases ordered by priority; clean weeks do not appear.
- Must exist: rule engine for all six rules (It2 for MEAL_PERIOD, It5 for the rest), queue priority (It2), queue UI (It4), seed data (It1, It6).
- What to point at: the finding labels, the amount column, the priority order, the two clean weeks absent from the queue.

## Step 2 (about 3 min): open the top case

Narrative: "The approver opens the top case. The copilot explains the violation with a citation to the agreement article and to the deal memo, shows the proposed action, and a draft return message."

- Action: open the case detail. Show the timecard events, the explanation, click a citation (the agreement passage opens at section 8.2 with the version shown), click the deal memo citation, show the proposed action and justification, show the draft message.
- Must exist: LangGraph pipeline detect, retrieve, explain, propose, draft, citation validation (It2), detail UI with clickable citations (It4), provider adapter (It2).
- What to point at: the numbers in the explanation come from the engine, not from the model (ADR-008); the citation key format; the audit entries already written for the suggestions.

## Step 3 (about 2 min): decide and resume

Narrative: "The approver edits the message and returns the timecard. The graph resumes from the checkpoint; everything lands in the audit log."

- Action: edit the draft, click Return. Show the status change, the resumed graph run (checkpoint id before and after), and the audit log entries: LLM suggestions, human decision with the edited text, executed action with actor and timestamp.
- Must exist: human checkpoint with interrupt and resume (It2), execute and audit nodes (It2), action buttons (It4).
- What to point at: the LLM had no write path; the human's identity is the actor; the original draft and the edited message are both in the log.

## Step 4 (about 1.5 min): source conflict

Narrative: "Here is a case where the deal memo and the agreement disagree. The system shows both sources and does not resolve the conflict silently."

- Action: open the SCALE_RATE case (SC-13). Show the deal memo rate next to the Schedule A scale, the explanation citing section 5.1 and Schedule A and article 3, the policy action escalate, and the escalation note.
- Must exist: SCALE_RATE rule and escalation path (It5), deal memo retrieval and dual citation (It2, It5).
- What to point at: escalation keeps the timecard untouched; a specialist decides; the model proposes but code determines the policy action (ADR-009).

## Step 5 (about 2 min): run the evaluation gate live

Narrative: "Before any version ships, the evaluation suite runs against known ground truth. All cases pass. Here is what happens when a version fails: the gate blocks."

- Action: run the eval command. Show the deterministic tier at 100% and the quality scores above thresholds. Then run the gate against the deliberately broken configuration (for example a prompt variant that cites the wrong section or a retrieval setting that drops the deal memo) and show the gate failing with the per-case reason.
- Must exist: eval harness and two-tier gate (It3), a committed broken variant (It3), traces visible in the tracing tool (It6) as an optional aside.
- What to point at: deterministic checks (cited section, passage exists for the effective version, action matches) versus quality checks (LLM judge with rubric, thresholds), and that a failed citation marks a case "needs human review" rather than falling back to a template.

## Closing line (about 30 s)

"An LLM engine that explains each exception with verifiable citations, proposes the resolution and drafts the message; deterministic code that detects, prioritizes, executes and logs; a human checkpoint in the graph; and an evaluation gate that measures the model against ground truth before any version ships."

## Rehearsal checklist (Iteration 6)

- Cold start under the agreed time with one command, seed included.
- Steps 1 to 5 complete in under 10 minutes with the narration.
- A fallback plan exists if the LLM provider is unreachable during the demo: show a recorded trace and the "needs human review" state the system enters (never a template).
