# Payroll Exception Triage Copilot

A reference implementation of exception triage for entertainment production payroll.

When a crew timecard trips a rule of the collective agreement (late meal, extended day, short rest, incomplete punches, a deal memo rate below scale, overdue eligibility paperwork), a deterministic rule engine detects the finding and computes the facts. An LLM then explains the finding with verifiable citations to the exact agreement passage and deal memo, proposes the resolution and drafts the return message. A human approver decides. Deterministic code executes the decision and writes an append-only audit trail. An evaluation gate measures the LLM against known ground truth before any version ships.

Everything in this repository is synthetic: the agreement, the rates, the crew, the productions and the timecards. No real company, product, union or guild is named or quoted.

## Status

Phase 0 (bootstrap) complete: documentation, decisions and tooling configuration. No application code yet. See `docs/progress/current-state.md` for the handoff and `docs/planning/current-plan.md` for the next steps.

## Layout

| Path | Purpose |
| --- | --- |
| `docs/requirements/` | Project brief, domain model, customer workflow, demo script |
| `docs/architecture/` | C4 views, LangGraph state machine, responsibilities |
| `docs/decisions/` | Architecture decision records (MADR style) |
| `docs/planning/` | Initial plan (frozen) and current plan |
| `docs/progress/` | Current state handoff and per-iteration logs |
| `docs/evidence/` | Evidence profile, assumptions, sources, data methodology |
| `backend/` | Python 3.12, FastAPI, LangGraph (Iteration 1 onward) |
| `frontend/` | React, TypeScript, Vite (Iteration 4) |
| `corpus/` | Synthetic agreement and deal memos |
| `data/` | Rule parameters and generated timecards |
| `evals/` | Evaluation cases and gate |
| `deployment/` | Docker compose and seed scripts |
| `observability/` | Tracing configuration |

## Working rules

See `AGENTS.md`. In short: the author commits by hand, no AI attribution anywhere, no real brands, English only, synthetic data only, and the LLM is the engine for explanation, proposal and drafting with no deterministic fallback.
