# ADR-015: Python dependency management with uv and the Iteration 1 dependency set

Status: Accepted
Date: 2026-10-07

## Context

The backend needs a reproducible Python 3.12 environment on the author's Windows machine, in containers, and for anyone cloning the repository. The hard constraints forbid agents from installing system-level tools, so the chosen tool must already be present or be the author's responsibility to install. `AGENTS.md` also requires an ADR before any new third-party dependency is used.

## Decision

- **Tool:** uv manages the Python version, the virtual environment and the lockfile. `backend/pyproject.toml` declares the project (`requires-python = ">=3.12,<3.13"`), `backend/.python-version` pins 3.12, and `backend/uv.lock` is committed. Commands: `uv sync`, `uv run pytest`, `uv run ruff check .`, `uv run ptc <command>`. Agents check that uv is installed and stop with instructions if it is not; they never install it.
- **Runtime dependencies (Iteration 1):** `fastapi` and `pydantic` (API and models from Iteration 2, declared now so the skeleton matches the plan), `pyyaml` (rule parameters, scenarios, deal memos), `jsonschema` (schema validation of the parameters file, ADR-007), `jinja2` (agreement template rendering, ADR-007).
- **Development dependencies:** `pytest`, `ruff` (lint and format, line length 100). Build backend: `hatchling`.
- **Later additions** (LangGraph, the LLM provider SDK, the PostgreSQL driver and checkpointer, OpenTelemetry exporters, the frontend toolchain) are added in the iteration that uses them, each named in that iteration's log; a new ADR is required only when the choice is not already covered by an accepted ADR (ADR-002, ADR-004, ADR-013 cover the main ones).

## Consequences

- One lockfile makes the gate result reproducible across machines; `uv sync` is the only setup step.
- Python 3.12 is enforced by the version pin and the `requires-python` upper bound; the environment on the author's machine resolved to a locally available 3.12 interpreter.
- The standard library's `argparse` is used for the CLI to avoid an extra dependency.
- The hook test harness and the git guard remain pure bash and do not depend on this environment.
