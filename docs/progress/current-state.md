# Current state

## Handoff

**Done**
- Iteration 000 (2026-10-07): bootstrap. Rules (`AGENTS.md`, `CLAUDE.md`), tool guardrails (`.claude/settings.json`, git guard hook tested with 86 cases), five validator subagents, requirements (brief, domain model, customer workflow, demo script), architecture overview, ADR-001 to ADR-014, initial and current plan, evidence set, this file.
- Vendor facts verified and recorded: tracing vendor regions and OpenTelemetry endpoint (ADR-004), checkpointer classes (ADR-013), coding assistant settings, hooks, imports and subagent format (ADR-014), eligibility deadline (sources S-05).

**Next**
- The author: run `git init`, confirm with `git status` that the private folder is not listed, make the first commit by hand.
- Then step **P1.I1.S1** (project skeletons: `backend/pyproject.toml` with Python 3.12, FastAPI and pytest; `evals/` and `data/` layout; `.env.example`). Acceptance: `pytest` runs. Validator: test-engineer. Followed by P1.I1.S2 (rule parameters YAML with schema and tests).

**Open decisions**
- OD-01: Queue priority formula (domain model, section 3, proposed). Owner: author. Decide in P1.I2.S7; record as a plan note or ADR if it changes the proposal.
- OD-02: Tier 2 thresholds and judge model (ADR-003). Owner: author. Decide in P1.I3.S3 after the baseline run.
- OD-03: Where the hook harness lives in the repository (`deployment/` or a `tools/` folder). Owner: author. Decide in P1.I1.S1.
- OD-04: LangGraph instrumentation library for OpenTelemetry (ADR-004 left it open). Owner: author. Decide in P1.I6.S1.
- OD-05: Whether filler crew with clean weeks are added to the seed beyond the six deal memo employees. Owner: author. Decide in P1.I1.S5.
- OD-06: Exact agreement wording for article 2 (jurisdiction) given that no Phase 1 rule depends on it. Owner: author. Decide in P1.I1.S3.

## Phase and iteration

Phase 0 complete. Phase 1, Iteration 1 (Domain and data) not started.

## What runs today

Nothing executable yet beyond the hook:

```
printf '{"tool_name":"Bash","tool_input":{"command":"git stash list"}}' | bash .claude/hooks/block-git-write.sh; echo $?   # 0
printf '{"tool_name":"Bash","tool_input":{"command":"git stash"}}' | bash .claude/hooks/block-git-write.sh; echo $?        # 2
```

## Known gaps

- No git repository initialized at the end of the bootstrap session (author action).
- No code, no dependencies, no data (by design for Phase 0).
- The hook harness (86 cases) exists only in the session scratchpad; recreate it in the repository in Iteration 1 (OD-03).

## Risks

- Schedule: six iterations in about two weeks; the vertical slice (ADR-005) is the mitigation.
- LLM judge calibration (ADR-003) may need more hand-labeled cases than planned.
- Provider availability during the demo: the rehearsal includes the "needs human review" fallback path (never a template).
