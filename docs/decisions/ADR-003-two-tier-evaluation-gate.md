# ADR-003: Two-tier evaluation gate

Status: Accepted
Date: 2026-10-07

## Context

The brief requires an evaluation gate that blocks deployment when the suite does not pass. A single pass or fail on free-text output is either too brittle (exact text match) or too lenient (any text passes). The LLM outputs have two kinds of properties: facts that can be checked mechanically (which section was cited, whether the passage exists, which action was proposed) and qualities that need judgment (is the explanation faithful to the facts, is the return message complete).

## Decision

The gate has two tiers and both must pass for a version to ship.

**Tier 1, deterministic checks, must pass 100% of cases:**
1. The cited section equals the expected section for every finding in the case.
2. Every cited passage exists verbatim in the corpus for the agreement version in force on the case's week ending (citation key version equals the effective version).
3. The proposed action equals the expected action (which equals the code policy action).
4. Negative cases (clean weeks) raise no finding and produce no case.

**Tier 2, quality checks, scored by an LLM judge with a written rubric, must meet thresholds:**
1. Explanation faithfulness: every factual statement in the explanation is supported by the engine facts or the cited passage; no number appears that the engine did not produce.
2. Return-message completeness: the draft names what is wrong, what the recipient must do, by when, and references the relevant section.

Thresholds (per metric, averaged and minimum per case) are set in Iteration 3 after a baseline run and recorded in the eval configuration; until then the scores are reported without blocking. The judge uses the adapter (ADR-002) with a pinned model and a fixed rubric stored in `evals/`.

A deliberately broken variant (for example a prompt that cites the wrong section or a retrieval setting that drops the deal memo) is committed so the gate's blocking behavior can be shown live (demo step 5).

## Consequences

- Eval cases carry structured expectations: rule ids, citation keys, action, engine facts. They are generated from the same YAML and scenario catalog as the data (ADR-007).
- The gate runs as one command and exits non-zero on failure; CI and the demo use the same command.
- The judge is itself an LLM and is calibrated in Iteration 3 against a handful of hand-labeled cases; disagreements are recorded in the iteration log.
- A case whose citation fails validation at runtime is routed to "needs human review"; in the gate the same case counts as a tier 1 failure.
