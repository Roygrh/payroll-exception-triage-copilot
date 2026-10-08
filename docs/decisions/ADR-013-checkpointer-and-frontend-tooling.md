# ADR-013: LangGraph checkpointer on the same PostgreSQL 16 instance; frontend with React, TypeScript and Vite

Status: Accepted
Date: 2026-10-07

## Context

The human checkpoint requires durable graph state: the run must pause, survive a restart, and resume with the human's decision. The brief fixes PostgreSQL 16 with pgvector for data and retrieval and React with TypeScript for the UI, but does not say where graph checkpoints live or which frontend tooling to use. Adding a second datastore for checkpoints would complicate the one-command compose stack.

## Decision

- Graph checkpoints are stored by LangGraph's PostgreSQL checkpointer in the same PostgreSQL 16 instance as the application data (a separate schema is acceptable). The checkpointer's `setup()` is run once by the seed or migration step.
- Verified on 2026-10-07 in the public LangGraph persistence documentation: the checkpointer classes are `PostgresSaver` and `AsyncPostgresSaver`, imported from `langgraph.checkpoint.postgres`, and the documentation's example calls `checkpointer.setup()` to create tables and indexes. The exact package name and the human-in-the-loop interrupt API are confirmed in Iteration 2 when the dependency is installed (the package name was not visible on the page fetched).
- Each exception case is one graph thread (thread id equals the case id) so that resume, audit and traces share one identifier.
- The frontend is React with TypeScript built with Vite, served as static files in compose and proxied to the API in development.

## Consequences

- Compose has three services in Phase 1: database, API (which also runs the graph), frontend. Tracing is external (ADR-004).
- Backups and resets of the demo database include checkpoints, which keeps "reset the demo" to one command.
- The hitl-workflow-validator checks that resume uses the stored thread and checkpoint ids and that the human's edited message is what executes.
