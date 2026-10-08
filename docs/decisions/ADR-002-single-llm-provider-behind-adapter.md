# ADR-002: Single LLM provider in Phase 1 behind a versioned, provider-agnostic adapter

Status: Accepted
Date: 2026-10-07

## Context

The brief allows one provider in Phase 1 and asks for a real multi-provider gateway in Phase 2. Building the gateway first would delay the vertical slice (ADR-005). At the same time, the Phase 2 port must exist from day one so nothing is thrown away.

## Decision

- Phase 1 uses one provider, Anthropic, for all three LLM functions (explain, propose, draft) and for the LLM judge in the evaluation gate.
- All provider access goes through an adapter with a versioned interface owned by this project (`LLMAdapter` v1): `complete(request) -> response` with structured input (system, messages, response schema, metadata for tracing) and structured output (text, parsed JSON when a schema is given, usage, latency, provider and model identifiers). The adapter is the only module that imports the provider SDK.
- Provider and model are selected by configuration (environment variables), not by code changes. A fake adapter implementing the same interface is used in unit and integration tests.
- The interface version is part of the adapter package name so that a breaking change produces v2 next to v1 rather than silent drift.

## Consequences

- Phase 2's gateway (second provider, optional local model, fallback, cost and latency control) is implemented behind the same interface; callers do not change.
- Prompt templates live with the graph nodes, not in the adapter; the adapter does not know about payroll.
- Model identifiers are pinned in configuration and recorded in traces and eval runs so that the gate result is attributable to a model version.
- Provider outages surface as adapter errors that the graph routes to "needs human review" (constraint 7); the adapter never returns templated text.
