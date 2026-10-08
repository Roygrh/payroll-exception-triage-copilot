# ADR-012: The repository is the durable system of record

Status: Accepted
Date: 2026-10-07

## Context

The project is built across many short sessions, by the author and by coding agents, with no shared chat memory. Context that lives in a conversation is lost at the end of the session. Requirements, decisions, plans and progress must survive and be findable by whoever opens the repository next.

## Decision

- `docs/` is the system of record. Requirements live in `docs/requirements/`, decisions in `docs/decisions/`, the plan in `docs/planning/`, state in `docs/progress/`, and the evidence basis in `docs/evidence/`.
- Every session starts by reading `docs/progress/current-state.md` (the Handoff block) and ends by rewriting it; every iteration produces `docs/progress/iterations/iteration-NNN.md` (procedure in `AGENTS.md`, section 5).
- `docs/planning/initial-plan.md` is frozen at bootstrap; `current-plan.md` is the living plan with a dated change log at the end.
- Decisions that change scope, architecture or process are ADRs; chat conclusions that are not written down do not exist.
- The authority hierarchy in `AGENTS.md` resolves conflicts between documents.

## Consequences

- Documentation updates are part of a step's definition of done, not an afterthought.
- Reviewers can reconstruct why the code looks the way it does from the ADR index.
- The private inputs folder (ADR-006) is explicitly not part of the system of record; everything needed to continue is in `docs/`.
