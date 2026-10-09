"""Action policy owned by code (ADR-009).

The policy table below is the only place that maps a situation to an action.
The rule engine and the expectation oracle both call it, so the ground truth
and the runtime cannot disagree on the action. The LLM proposes an action and
a justification; the graph compares the proposal with the policy action and
routes a mismatch to "needs human review" (ADR-009, reconciliation).
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from payroll_triage.calc import MealFacts, tenths
from payroll_triage.params import RuleParameters
from payroll_triage.timecards import TimecardDay

APPROVE = "approve"
RETURN = "return"
ESCALATE = "escalate"
NONE = "none"

ACTIONS = (NONE, APPROVE, RETURN, ESCALATE)
SEVERITY = {APPROVE: 1, RETURN: 2, ESCALATE: 3}


class Situation(StrEnum):
    """The rows of the ADR-009 policy table."""

    PREMIUM_COMPLETE_PLAUSIBLE = "premium_complete_plausible"
    INCOMPLETE_OR_IMPLAUSIBLE = "incomplete_or_implausible"
    COMPLIANCE_OR_CONFLICT = "compliance_or_conflict"


POLICY_TABLE: dict[Situation, str] = {
    Situation.PREMIUM_COMPLETE_PLAUSIBLE: APPROVE,
    Situation.INCOMPLETE_OR_IMPLAUSIBLE: RETURN,
    Situation.COMPLIANCE_OR_CONFLICT: ESCALATE,
}

POLICY_ROW_TEXT: dict[Situation, str] = {
    Situation.PREMIUM_COMPLETE_PLAUSIBLE: (
        "Premium pay finding (late meal, extended day, rest invasion) with complete, "
        "plausible data: approve; code adds the premium line."
    ),
    Situation.INCOMPLETE_OR_IMPLAUSIBLE: (
        "Incomplete or implausible data (missing or out-of-order entries, meal under the "
        "minimum, implausible day length): return for correction."
    ),
    Situation.COMPLIANCE_OR_CONFLICT: (
        "Compliance block (eligibility overdue) or source conflict (deal memo below scale): "
        "escalate to a payroll specialist."
    ),
}


def policy_action(situation: Situation) -> str:
    return POLICY_TABLE[situation]


def day_is_plausible(day: TimecardDay, params: RuleParameters) -> bool:
    """Complete, chronological entries and an elapsed day within the plausibility limit."""
    if not day.is_chronological():
        return False
    assert day.call is not None and day.wrap is not None
    return tenths(day.wrap - day.call) <= params.plausibility.max_day_hours


def premium_situation(plausible: bool) -> Situation:
    """Extended day and rest invasion: approve when plausible, otherwise return."""
    if plausible:
        return Situation.PREMIUM_COMPLETE_PLAUSIBLE
    return Situation.INCOMPLETE_OR_IMPLAUSIBLE


def meal_situation(facts: MealFacts, plausible: bool) -> Situation:
    """A short meal is treated as a recording problem (agreement 8.2); a late meal on a
    plausible day is a premium finding."""
    if facts.is_short or not plausible:
        return Situation.INCOMPLETE_OR_IMPLAUSIBLE
    return Situation.PREMIUM_COMPLETE_PLAUSIBLE


def completeness_situation() -> Situation:
    return Situation.INCOMPLETE_OR_IMPLAUSIBLE


def compliance_situation() -> Situation:
    return Situation.COMPLIANCE_OR_CONFLICT


def combined_action(actions: Iterable[str]) -> str:
    """Most severe action wins (escalate > return > approve); 'none' without findings."""
    best = NONE
    for action in actions:
        if action not in SEVERITY:
            raise ValueError(f"unknown policy action {action!r}")
        if best == NONE or SEVERITY[action] > SEVERITY[best]:
            best = action
    return best
