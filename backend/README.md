# Backend

Python 3.12 project managed with uv (ADR-015). Iteration 1 contains the rule parameter loader, the agreement renderer, the deal memo loader, the seeded timecard generator and the evaluation manifest builder. The API, rule engine and graph arrive in Iteration 2.

Commands (run from this folder):

```
uv sync                      # create the virtual environment from uv.lock
uv run pytest                # tests
uv run ruff check .          # lint
uv run ptc render-agreement  # render corpus/cgma-2026.1.md from the template and the YAML
uv run ptc generate-data     # write data/generated/ from data/scenarios.yaml (seeded)
uv run ptc build-manifest    # write evals/cases/manifest.yaml
uv run ptc check             # verify that committed outputs equal regenerated outputs
```
