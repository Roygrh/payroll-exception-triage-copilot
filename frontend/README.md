# Approver UI

React, TypeScript and Vite (ADR-013) with Tailwind CSS, Vitest and React Testing Library (ADR-020). Node 24.11.0 or later.

## Run against the local API

Two terminals:

```
# backend/  (needs the database up, migrated and seeded; see docs/progress/current-state.md)
uv run ptc serve                 # API on http://127.0.0.1:8000

# frontend/
npm install                      # once
npm run dev                      # UI on http://localhost:5173
```

The dev server forwards `/api/...` to `http://127.0.0.1:8000/...` (the API has no prefix), so the API needs no CORS change. Set `PTC_API_URL` to point the proxy at another address.

## Commands

```
npm run build    # type check, then the static build in dist/
npm test         # component tests; the API is mocked, no backend needed
npm run lint
```

## Screens

- `#/` exception queue: counters, "Ingest week" (one LLM call per case with a finding), rows in the API's priority order.
- `#/cases/{id}` case detail: the finding day as HH:MM, engine facts, the validated explanation and proposal with citation buttons, the cited passage, the passages retrieved and the model call; Approve, Return, Escalate.
- `#/cases/{id}/message` confirm the message drafted after Return or Escalate (one LLM call); the body is editable and starts empty when the draft needs review.
- `#/cases/{id}/audit` executed banner and the audit trail.

The approver is the catalog's demo approver (`GET /context`), self-asserted in Phase 1 (OD-10).
