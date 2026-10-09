# Assumptions

Each assumption is tagged with its origin: **from brief** (the original project brief), **from approved decision** (an ADR), or **introduced in bootstrap** (chosen while writing these documents and open to revision). Status: open, confirmed, refuted. Update this file whenever a status changes (AGENTS.md, section 5).

| Id | Assumption | Origin | Status | Where it matters |
| --- | --- | --- | --- | --- |
| A-01 | Pay calculation is already automated in platforms of this category; the human effort is in exception queues | from brief | open (hypothesis per ADR-001) | product thesis, demo narration |
| A-02 | The target user is the approver or production accountant working a personal queue before the payroll run | from brief | open | persona, queue design |
| A-03 | A timecard records events (call, meal out, meal in, wrap) per day rather than totals | from brief | confirmed by public product documentation | timecard model, generator |
| A-04 | Approval statuses follow the chain Draft to Paid with Incomplete and Rejected side states | from brief | confirmed by public product documentation | timecard model |
| A-05 | Deal memos are the per-person source of truth and can conflict with the agreement scale | from brief | open | SCALE_RATE, demo step 4 |
| A-06 | Eligibility paperwork is tracked per offer with overdue counters | from brief | confirmed by public product documentation | ELIGIBILITY_DOC |
| A-07 | One LLM provider is sufficient for Phase 1 if the adapter is provider-agnostic | from approved decision (ADR-002; provider changed by ADR-016) | confirmed in Iteration 2: one OpenAI-compatible adapter serves Groq, OpenAI and Ollama by configuration; Anthropic optional | adapter |
| A-08 | Deterministic checks can be required at 100% without making the gate brittle, because they test structured outputs | from approved decision (ADR-003) | open until Iteration 3 baseline | gate |
| A-09 | An LLM judge with a rubric is a usable proxy for explanation faithfulness and message completeness | from approved decision (ADR-003) | open until calibration in Iteration 3 | gate |
| A-10 | Langfuse Cloud US region is acceptable for synthetic demo data | from approved decision (ADR-004) | confirmed (no personal data in traces) | tracing |
| A-11 | Normal overtime never needs a human decision | from approved decision (ADR-010) | open | rule set |
| A-12 | Code can own the action policy without making the LLM's proposal redundant (the justification and the requested correction are the value) | from approved decision (ADR-009) | open | propose node, UI |
| A-13 | Times stored as decimal hours from midnight of the shift date, in tenths of an hour (values above 24 for next-day wraps), are sufficient and unambiguous | introduced in bootstrap, refined in Iteration 1 | open | generator, engine |
| A-14 | Payroll week is Sunday to Saturday with week ending on Saturday | introduced in bootstrap | open | generator, agreement article 4 |
| A-15 | A meal shorter than 30 minutes is a data problem (return) rather than a premium case | introduced in bootstrap | open | MEAL_PERIOD policy |
| A-16 | A late meal with complete, plausible data is approved with the premium added by code (no human correction needed) | from approved decision (ADR-009) | open | MEAL_PERIOD policy |
| A-17 | Rest hours are measured from wrap to the next calendar day's call plus 24 hours; invaded hours are paid at 2.0x | introduced in bootstrap | open | REST_PERIOD |
| A-18 | The queue priority formula (urgency, severity, amount tier, days late) is a reasonable first ordering | introduced in bootstrap | implemented in Iteration 2 (weights in the YAML `queue` block); author confirmation pending (OD-01) | queue |
| A-19 | The exception queue consumes timecards in status Ready for approver 1 | introduced in bootstrap | open | ingestion, UI |
| A-20 | Hire state versus work state matters to the agreement but no Phase 1 rule depends on it | introduced in bootstrap | open | agreement article 2, deal memo fields |
| A-21 | Six rules and 18 scenarios fit the brief's ranges (5 to 7 rules, 15 to 20 cases) | introduced in bootstrap | confirmed against the brief | domain model |
| A-22 | The LangGraph PostgreSQL checkpointer can share the application database without conflicts | from approved decision (ADR-013) | confirmed in Iteration 2 (checkpoint tables next to the application tables; pause and resume across a graph rebuild tested) | compose, migrations |
| A-23 | A pure-bash hook is portable enough for the author's Windows plus Git Bash setup and for other contributors | from approved decision (ADR-014) | confirmed on the author's machine | tooling |
| A-25 | A 20-billion-parameter open-weights model with strict JSON schema output can produce grounded explanations, proposals and drafts that pass code validation | from approved decision (ADR-016) | open until the showcase run and the Iteration 3 baseline | prompts, gate |
| A-26 | A small local embedding model (384 dimensions) ranks the governing section and the deal memo in the top results for every rule | from approved decision (ADR-017) | confirmed for MEAL_PERIOD in Iteration 2 (integration test); open for the other rules | retrieval |
| A-24 | The 3 business day eligibility deadline counts business days after the first day of work for pay | introduced in bootstrap (verified against the public source) | confirmed | ELIGIBILITY_DOC |
