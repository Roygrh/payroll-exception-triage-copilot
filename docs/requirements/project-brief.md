# Project brief: Payroll Exception Triage Copilot

This is the English, brand-free rendering of the original project brief, with the changes introduced by accepted decisions (ADR-001 to ADR-014) applied in place and listed in section 12. It is the third authority after the hard constraints in `AGENTS.md` and the ADRs.

## 1. Purpose

A demo and portfolio application that shows how an LLM-centered copilot can triage payroll exceptions for entertainment productions while keeping calculation, execution and audit in deterministic code and keeping the human approver in charge of every decision.

## 2. Why this project exists

- The target role is an AI forward deployed engineer at a company whose business is payroll and financial back office for entertainment productions (film, television, streaming, commercials, live events). The role asks for direct work with customers and stakeholders, LLM, agent, retrieval and workflow automation solutions, copilots and decision support systems, graph-based agent orchestration, SQL, cloud (one major provider as primary), evaluation frameworks and guardrails, and end-to-end ownership from discovery to adoption.
- Companies in this segment differentiate on expert human support. The right framing for any AI solution is therefore to amplify their experts and approvers, not to replace them.
- Use of the project: (a) a demo that can be shown in an interview on short notice; (b) otherwise, a public portfolio piece that grows in scope.
- The product names no real company, product, union or guild. The domain is generic "entertainment production payroll" with fictitious names throughout.

## 3. The business domain

The platform category covers the cycle: crew onboarding, time capture, pay calculation by rules, approvals, invoices, payment. The product mirrors this vocabulary (details in `customer-workflow.md` and `domain-model.md`).

**Onboarding**
- Crew member: a person registered on a production. One crew member has zero or more offers (one per position, condition or period).
- Offer (start packet): digital hiring with structured fields: season, union, occupation (numeric code plus title), work schedule, department, hire state, hire city, work state, primary work city, start date, rate, allowances.
- Deal memo: the individual's contractual conditions (rate, position, applicable rules). Source of truth per person.
- Document compliance: explicit status tracking, for example the employment eligibility verification form with visible overdue counters.
- Workflow: create crew, create offer, internal approvals, send, employee signature, eligibility review, onboarding complete. Role-based permissions protect compensation data.

**Timekeeping**
- A timecard records workday events per day, not a total: day type, work location, call time, meal 1 out, meal 1 in, wrap. The engine derives hours, overtime and penalties from these events by applying the union agreement and the deal memo.
- Multi-level approval chain with statuses: Draft, Incomplete, Rejected, Ready for employee, Ready for dept head, Ready for approver 1, 2, 3, Submitted (to the payroll processor), Processing, Paid.
- Invoices have their own workflow (Processing, Review, Edits, Revisions, Resubmitted, Hold, Invoice Approved, Paid); each invoice groups several timecards.
- Existing features that reveal pain: automatic account coding, bulk edit and bulk approvals, filters by union, personal queues ("ready for me").

**Domain conclusion.** Pay calculation is already deterministic and solved. The operational pain is in the human exception queues: rejected, incomplete, rule-violating or overdue timecards that approvers and production accountants must investigate case by case before the payroll run. Per ADR-001 this is a hypothesis to validate in discovery; volumes and time per exception are unknown.

## 4. The product

**Working name:** Payroll Exception Triage Copilot.

**Pitch:** an LLM-powered copilot that, for each timecard exception, reasons over the union agreement and the deal memo, explains the violation with verifiable citations to the exact passage, proposes the resolution and drafts the return message. Pay calculation and action execution stay in deterministic code. The human always decides.

**Target user:** the approver or payroll accountant working an exception queue.

**Non-negotiable requirement:** the LLM is the central, visible engine of the product, not an accessory. A purely deterministic system does not meet the project's objective. Explanation, proposal and drafting are always produced by the LLM; if the call fails or citations do not validate, the case is marked "needs human review" (no deterministic fallback).

**Architecture principle (the selling argument):** the LLM does the cognitive work (explain, propose, draft, answer); deterministic code does what an auditor demands (detect, compute, prioritize, execute, log); an evaluation gate measures the LLM against known truth before any version ships.

## 5. LLM engine functions

| # | Function | Description | Phase |
| --- | --- | --- | --- |
| 1 | Exception Explainer (retrieval-grounded) | Given an exception, retrieves passages from the agreement and the deal memo (hybrid semantic plus keyword retrieval) and writes the plain-language explanation with a link to the cited passage. Example: "This timecard violates Section 8.2 (meal periods): the first meal began 6.5 hours after call; the agreement requires it within 6.0 hours." | 1 |
| 2 | Resolution Proposer | Proposes the action (approve, return, escalate) with a reasoned justification; never executes. The action policy is owned by code (ADR-009); the LLM's proposal must agree with the policy action or the case goes to human review. | 1 |
| 3 | Return-Message Drafter | Drafts the message to the employee or department head stating what must be corrected; the human edits and sends. | 1 |
| 4 | Rules Q&A | Approver chat about rules with citations, effective-date filtering, and refusal with a route to a specialist when retrieval does not support the answer. | 2 |

**Orchestration:** LangGraph as a state machine per exception: detect (code), retrieve, explain (LLM), propose (LLM), draft (LLM), validate citations (code), human checkpoint (pause and resume), execute (code), audit (code), with a "needs human review" path. The graph with human checkpoint and resume is a demo piece in itself.

Effective-date filtering and permission-filtered retrieval are deferred to Phase 2 (ADR-011); the corpus schema carries the fields from day one.

## 6. Deterministic components (the safety perimeter)

- **Rule engine:** six simplified agreement rules in pure code that detect findings over timecard events: meal period, extended day, rest period, time entry completeness, scale rate, eligibility document (ADR-010: normal daily and weekly overtime is calculated but never raises an exception). The engine computes all facts (hours, minutes late, increments, amounts) and generates the ground truth the LLM is evaluated against (ADR-008).
- **Action policy:** premium pay with complete, plausible data: approve (code adds the premium line); incomplete or implausible data: return; compliance block or source conflict: escalate. Several findings: most severe wins (ADR-009).
- **Queue prioritization:** order by amount involved, days late and proximity of the payroll run. Business rules, not LLM.
- **Action execution:** approve, return and escalate run under the user's identity; the LLM has no write permissions.
- **Citation validation:** before an explanation is shown, code verifies that every cited passage exists in the corpus and belongs to the version in force. A claim without a retrievable citation is discarded and the case is marked "needs human review".
- **Append-only audit log:** every LLM suggestion, every human decision and every action, with timestamp and actor.

## 7. Synthetic corpus

- A fictitious "Crew Guild Master Agreement" (CGMA), 15 to 20 pages, generated from a template whose numbers come from the rule parameters YAML (ADR-007). No text is copied from real agreements; realism lives in the structure: numbered sections, definitions, occupation codes with rates and allowances, meal, overtime and rest rules expressed over workday events, document deadlines, jurisdiction differences (hire state versus work state).
- Six synthetic deal memos: employee, occupation code, guild, rate, allowances, season, department, hire state, work state, start date, and conditions that can conflict with the agreement scale (the system shows both sources; it never resolves the conflict silently).
- Versioning with effective dates: Phase 2 adds a second agreement version with a different effective range; retrieval filters by the week-ending date before ranking and every answer declares which version it cites.
- Data generator: productions, crew, timecards with events, weeks (week ending), with clean cases and cases that violate each rule (18 scenarios, see `domain-model.md`).

## 8. Phases

**Phase 1 (demo-ready, target about two weeks)**
- LLM functions 1 to 3, one default provider (gpt-oss-20b on GroqCloud free tier, ADR-016) behind a versioned provider-agnostic adapter (ADR-002); other OpenAI-compatible endpoints and Anthropic by configuration.
- Corpus: one agreement (one version) plus six deal memos. Rule engine with six rules.
- UI: prioritized exception queue plus detail view (timecard, explanation with clickable citations, proposal, draft message) plus human-in-the-loop buttons.
- Evals: 18 cases with known resolution plus a two-tier gate (ADR-003) that blocks deployment when it fails.
- Traces with OpenTelemetry and Langfuse Cloud (ADR-004). Docker compose, one-command start with demo seed.
- Delivery order: vertical slice MEAL_PERIOD end to end first (ADR-005), then widen.

**Phase 2 (portfolio)**
- Real multi-provider gateway (second provider, optional local model), fallback, cost and latency control.
- Function 4 (Rules Q&A), ambiguous-case classifier with confidence score.
- Second agreement version with effective dates (temporal filter demo), citation fidelity as a formal metric, expanded eval suite on a dedicated LLM evaluation framework.
- Permission-filtered retrieval (ADR-011).
- Audit viewer and metrics dashboard. Self-hosted tracing (ADR-004). Serverless deployment on the primary cloud provider with infrastructure as code.

**Design rule between phases:** Phase 1 leaves the Phase 2 ports ready (model adapter, effective-date and permission fields in the corpus schema, extensible eval schema). Nothing from Phase 1 is discarded in Phase 2.

## 9. Stack

Python 3.12 with FastAPI (backend), LangGraph (orchestration, checkpointer on PostgreSQL per ADR-013), PostgreSQL 16 with pgvector (data and hybrid retrieval), React with TypeScript and Vite (queue UI, ADR-013), OpenTelemetry with Langfuse (LLM traces), Docker compose. Documentation: C4 model plus one ADR per relevant decision. Automated tests from the start.

## 10. Demo script (10 minutes, governs the design)

See `demo-script.md`. If a component does not appear in that script, it is not built in Phase 1.

## 11. Development constraints (mandatory)

- Git: the author makes commits by hand. Development agents are forbidden to run any git command that modifies state; read-only inspection is allowed. Enforced by a hook (ADR-014).
- No AI signatures: no co-author trailer or mention of AI tools in commit messages or repository files.
- No real brands inside the product, code, data or docs: generic domain with fictitious names.
- The agreement text and all data are synthetic; no copies of real documents.
- Repository content in English; no em dashes.

## 12. Success criterion

To be able to say in an interview: "I built a working reference of exception triage for entertainment payroll: an LLM engine that explains each exception with verifiable citations over a versioned agreement corpus, proposes the resolution and drafts the return message; deterministic code detects, prioritizes, executes and logs; human checkpoints via LangGraph; and an evaluation gate that measures the LLM against known ground truth before any version ships. I can show it in 10 minutes."

## 13. Differences between the original brief and this document

| Topic | Original brief | Applied here | Decision |
| --- | --- | --- | --- |
| Evidence status of the problem | Stated as a conclusion | Grounded synthetic problem; the exception-queue pain is a hypothesis; volumes unknown | ADR-001 |
| LLM provider in Phase 1 | Anthropic or one other named provider | Default gpt-oss-20b on GroqCloud (free tier) through an OpenAI-compatible adapter; Anthropic optional behind the same versioned interface | ADR-002, ADR-016 |
| Evaluation gate | Gate blocks if not all cases pass | Two tiers: deterministic checks at 100%, quality checks by threshold with an LLM judge | ADR-003 |
| Tracing | OpenTelemetry plus Langfuse (hosting unspecified) | Langfuse Cloud, US region, in Phase 1; self-hosting in Phase 2 | ADR-004 |
| Build order | Not specified | Vertical slice MEAL_PERIOD end to end first | ADR-005 |
| Sources naming real organizations | Not addressed | Stay in the gitignored private folder; in-repo evidence is generic | ADR-006 |
| Where numbers live | Not addressed | Rule parameters YAML is the single source of truth; agreement numbers inserted by template | ADR-007 |
| What the LLM computes | Implied | Nothing: the rule engine computes all facts | ADR-008 |
| Who decides the proposed action | LLM proposes | Code owns the action policy; the LLM proposes and justifies; mismatch goes to human review | ADR-009 |
| Overtime rules | Daily and weekly overtime listed among detection rules | Overtime is calculated, never an exception; only a workday over 12 h raises EXTENDED_DAY | ADR-010 |
| Retrieval filters | Effective-date and permission filtering in Function 1 (Phase 1) | Deferred to Phase 2; schema fields exist from day one | ADR-011 |
| Embeddings | Not specified | Small local open-source model, no embeddings API; hybrid retrieval fused by reciprocal rank fusion | ADR-017 |
| System of record | Not addressed | The repository (docs/) is the durable system of record | ADR-012 |
| Checkpointer and frontend tooling | Not specified | LangGraph checkpointer on the same PostgreSQL 16 instance; React with TypeScript and Vite | ADR-013 |
| Git guard | Policy only | Policy plus a PreToolUse hook that blocks state-modifying git commands | ADR-014 |
| Rule count and eval count | 5 to 7 rules, 15 to 20 cases | 6 rules, 18 scenarios | Domain model |
| Deal memo count | 5 to 8 | 6 | Domain model |
