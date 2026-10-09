"""Rule engine: detects findings and computes every fact (ADR-008), applies the
code-owned policy (ADR-009) and the queue priority. Iteration 2 wires MEAL_PERIOD;
the other rules arrive in Iteration 5."""

from payroll_triage.engine.rules import Detection, Finding, detect, wired_rules

__all__ = ["Detection", "Finding", "detect", "wired_rules"]
