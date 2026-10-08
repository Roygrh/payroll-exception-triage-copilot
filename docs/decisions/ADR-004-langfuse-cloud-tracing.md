# ADR-004: Langfuse Cloud (US region) for Phase 1 tracing; self-hosting in Phase 2

Status: Accepted
Date: 2026-10-07

## Context

The brief asks for LLM traces with OpenTelemetry and Langfuse, with Docker compose for a one-command local start. Self-hosting Langfuse adds several infrastructure components to the compose stack and would slow down Phase 1. The project also wants the trace backend to be swappable, which OpenTelemetry provides.

## Decision

- Phase 1 exports OpenTelemetry traces to Langfuse Cloud in the US data region. Keys and endpoint come from environment variables; nothing is hard-coded.
- Phase 2 moves to a self-hosted Langfuse (Docker compose for local, Kubernetes or managed services for cloud) using the same OpenTelemetry exporter, so the application code does not change.
- Spans are emitted per graph node and per LLM call, carrying case id, rule ids, model identifier, adapter version, token usage and latency; no personal data beyond the synthetic employee name.

## What was checked (2026-10-07)

Public vendor documentation was read for this record:

- Data regions page: Langfuse Cloud offers a US region hosted on a major cloud provider in us-west-2 (Oregon), an EU region in eu-west-1 (Ireland) and a JP region in ap-northeast-1; the platform runs mainly on that cloud provider and a managed ClickHouse service.
- OpenTelemetry page: Langfuse accepts OTLP over HTTP (JSON and protobuf, no gRPC) at `https://us.cloud.langfuse.com/api/public/otel` for the US region (EU: `https://cloud.langfuse.com/api/public/otel`); traces-only collectors use the `/v1/traces` suffix. Authentication is HTTP Basic with the base64 of `public_key:secret_key`; an ingestion-version header enables real-time ingestion.
- Self-hosting page: the open-source edition is MIT licensed; Docker compose is documented for local use and testing (single machine, no high availability), Kubernetes with Helm for production; required components are PostgreSQL, ClickHouse, Redis or Valkey, and S3-compatible blob storage, plus the web and worker containers.

Not verified in this session: pricing tiers and retention limits of the free cloud plan, and the exact LangGraph instrumentation package to use (the OpenTelemetry page lists third-party instrumentation libraries for LangChain; the choice is made in Iteration 6).

## Consequences

- `.env.example` documents `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_HOST` (US host by default) and the OTel exporter variables.
- The compose stack in Phase 1 has no tracing containers; traces are visible in the vendor UI during the demo (optional aside in demo step 5).
- Phase 2 adds the self-hosting compose profile and verifies that the same spans arrive.
- If the cloud service is unreachable, the application must keep working: the exporter fails open (logs a warning) and never blocks a graph run.
