# ADR-011: Permission-filtered retrieval and the effective-date filter deferred to Phase 2

Status: Accepted
Date: 2026-10-07

## Context

The brief's Function 1 describes hybrid retrieval filtered by effective date and by permissions. Phase 1 has one agreement version and one user role, so neither filter changes any result in the demo, while both add schema, test and UI work. Phase 2 introduces the second agreement version (where the date filter matters) and role-based access to deal memo data (where the permission filter matters).

## Decision

- Phase 1 implements hybrid retrieval (semantic plus keyword) without filtering by effective date or permissions.
- The corpus schema carries the fields from day one: `agreement_versions.effective_from` and `effective_to`, `corpus_chunks.version`, `corpus_chunks.permission_scope`, and deal memo chunks tagged with the employee and department they belong to. Citation keys include the version.
- Every answer declares which version it cites (the key format already does), so the Phase 2 filter is an additive query predicate, not a redesign.
- Phase 2 implements: effective-date filtering by the case's week ending before ranking, and permission filtering by the requesting user's role and department.

## Consequences

- The citation validator in Phase 1 still checks that the cited version is the version in force for the week ending; with one version this is trivially true but the check exists and is tested.
- Eval cases carry the week ending so that Phase 2 can add versioned expectations without changing the manifest format.
- The demo must not claim that date or permission filtering exists in Phase 1.
