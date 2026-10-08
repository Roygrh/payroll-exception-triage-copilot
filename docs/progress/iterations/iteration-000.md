# Iteration 000: Bootstrap

Date: 2026-10-07
Phase: 0
Scope: documentation and tool configuration only. No application code, no dependencies installed, no synthetic data generated.

## Summary

The repository was bootstrapped from the private inputs: rules for agents, tool guardrails (permission deny list, git guard hook, attribution disabled), five validator subagents, requirements, architecture, fourteen ADRs, the plan, the evidence basis and this progress log. Vendor facts were verified against public documentation and recorded in the ADRs. The working folder was not yet a git repository at the end of the session; the author initializes it and makes the first commit by hand.

## Steps completed

| Step | Artifact | Acceptance evidence | Validators |
| --- | --- | --- | --- |
| P0.I0.S1 | `.gitignore` | Private folder excluded by the first rule. `git status` could not be run because the folder is not a git repository yet, and initializing one is a state-modifying command reserved for the author; the check is the author's first action after `git init` (see Handoff). | author |
| P0.I0.S2 | `AGENTS.md`, `CLAUDE.md` | Import syntax `@AGENTS.md` verified against the memory documentation; CLAUDE.md contains only the import | author |
| P0.I0.S3 | `.claude/settings.json`, `.claude/hooks/block-git-write.sh` | JSON parsed; hook harness of 86 payloads all behaved as expected, including `git stash list` allowed and `git stash` blocked; hook observed live in the session blocking a shell command | hook harness (ADR-014) |
| P0.I0.S4 | `.claude/agents/` (5 files) | Frontmatter fields verified against the subagents documentation; output format PASS, FAIL, BLOCKED with severity, evidence, location, recommendation | author |
| P0.I0.S5 | `docs/requirements/` (4 files) | Brand-free, English; differences from the original brief listed in the brief's section 13 | author |
| P0.I0.S6 | `docs/architecture/overview.md` | C4 context and container (Mermaid), state machine with needs-human-review path, responsibilities table | author |
| P0.I0.S7 | `docs/decisions/` (14 ADRs plus index) | MADR sections; verification notes in ADR-004, ADR-013, ADR-014 | author |
| P0.I0.S8 | `docs/planning/`, `docs/progress/`, `docs/evidence/` | Initial and current plan identical; handoff block present; 24 assumptions tagged | author |
| P0.I0.S9 | Hygiene scans | Forbidden-term scan, em dash scan, phone number and compensation figure scan outside the private folder: all empty (recorded in Notes) | author |

## Deviations from the plan

- None in scope. One interpretation recorded in `AGENTS.md`: technology vendors named in accepted ADRs are allowed in the repository; domain brands are not.

## Validator findings carried forward

- None (no code yet). The hook harness lives in the session scratchpad and is described in ADR-014; Iteration 1 should add it to the repository under `deployment/` or a `tools/` folder so it can be rerun.

## Metrics

- Hook harness: 86 cases, 86 as expected.
- Files created: see `current-state.md`.

## Open decisions raised

See the Handoff block in `current-state.md`.

## Notes

- Settings that could not be verified in this session: whether hooks defined in project settings fire for subagents in every case (the documentation says hooks merge across settings levels; the live block observed in this session came from the main session), and the free-plan limits of the tracing vendor.
- The folder was not a git repository, so `git init` and the first commit are the author's first actions. `.gitattributes` normalizes line endings; the hook script must stay LF (declared there).
