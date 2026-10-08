# Architecture decision records

MADR style: context, decision, consequences, status. New decisions get the next number; superseding is explicit in both records.

| ADR | Title | Status | Date |
| --- | --- | --- | --- |
| [ADR-001](ADR-001-evidence-profile-e3.md) | Evidence profile E3: grounded synthetic problem, synthetic data | Accepted | 2026-10-07 |
| [ADR-002](ADR-002-single-llm-provider-behind-adapter.md) | Single LLM provider in Phase 1 behind a versioned, provider-agnostic adapter | Accepted | 2026-10-07 |
| [ADR-003](ADR-003-two-tier-evaluation-gate.md) | Two-tier evaluation gate | Accepted | 2026-10-07 |
| [ADR-004](ADR-004-langfuse-cloud-tracing.md) | Langfuse Cloud (US region) for Phase 1 tracing; self-hosting in Phase 2 | Accepted | 2026-10-07 |
| [ADR-005](ADR-005-vertical-slice-first.md) | Vertical slice first: MEAL_PERIOD end to end | Accepted | 2026-10-07 |
| [ADR-006](ADR-006-private-sources-folder.md) | Sources naming real organizations stay in the gitignored private folder | Accepted | 2026-10-07 |
| [ADR-007](ADR-007-rule-parameters-yaml-single-source.md) | Rule parameters YAML is the single source of truth | Accepted | 2026-10-07 |
| [ADR-008](ADR-008-llm-never-computes.md) | The LLM never computes | Accepted | 2026-10-07 |
| [ADR-009](ADR-009-action-policy-owned-by-code.md) | Action policy owned by code | Accepted | 2026-10-07 |
| [ADR-010](ADR-010-overtime-is-not-an-exception.md) | Normal overtime is calculated, never an exception | Accepted | 2026-10-07 |
| [ADR-011](ADR-011-defer-permission-and-effective-date-filters.md) | Permission-filtered retrieval and effective-date filter deferred to Phase 2 | Accepted | 2026-10-07 |
| [ADR-012](ADR-012-repository-as-system-of-record.md) | The repository is the durable system of record | Accepted | 2026-10-07 |
| [ADR-013](ADR-013-checkpointer-and-frontend-tooling.md) | LangGraph checkpointer on PostgreSQL 16; React, TypeScript and Vite frontend | Accepted | 2026-10-07 |
| [ADR-014](ADR-014-git-guard-hook.md) | PreToolUse hook blocks state-modifying git commands | Accepted | 2026-10-07 |
| [ADR-015](ADR-015-python-tooling-uv.md) | Python dependency management with uv and the Iteration 1 dependency set | Accepted | 2026-10-07 |

Template for new records:

```markdown
# ADR-NNN: Title

Status: Proposed | Accepted | Superseded by ADR-MMM
Date: YYYY-MM-DD

## Context
## Decision
## Consequences
```
