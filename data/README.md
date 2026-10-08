# Data

- `rule-parameters.yaml`: the single source of truth for every domain number (ADR-007), validated by `rule-parameters.schema.json`.
- `scenarios.yaml`: the scenario catalog (18 scenarios plus filler crew) and the generator seed. Mirrors `docs/requirements/domain-model.md`, section 7.
- `generated/`: output of `uv run ptc generate-data` (run from `backend/`): timecards and filler deal memos. Committed; regenerating with the same seed must produce identical files (`uv run ptc check`).
