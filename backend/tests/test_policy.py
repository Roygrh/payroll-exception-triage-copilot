"""One test per row of the ADR-009 policy table, plus combination and plausibility."""

from __future__ import annotations

import datetime as dt

import pytest

from payroll_triage import calc, policy
from payroll_triage.params import load_parameters
from payroll_triage.policy import (
    APPROVE,
    ESCALATE,
    NONE,
    POLICY_TABLE,
    RETURN,
    Situation,
    combined_action,
    completeness_situation,
    compliance_situation,
    day_is_plausible,
    meal_situation,
    policy_action,
    premium_situation,
)
from payroll_triage.timecards import TimecardDay


@pytest.fixture(scope="module")
def p():
    return load_parameters()


def _day(call, meal_out, meal_in, wrap) -> TimecardDay:
    return TimecardDay(
        date=dt.date(2026, 3, 10),
        weekday="Tue",
        day_type="1-Work",
        work_location="S-Stage",
        call=call,
        meal_out=meal_out,
        meal_in=meal_in,
        wrap=wrap,
    )


def test_table_has_exactly_the_three_adr_rows():
    assert set(POLICY_TABLE) == set(Situation)
    assert len(POLICY_TABLE) == 3


def test_row_premium_complete_plausible_approves():
    assert policy_action(Situation.PREMIUM_COMPLETE_PLAUSIBLE) == APPROVE
    assert policy_action(premium_situation(plausible=True)) == APPROVE


def test_row_incomplete_or_implausible_returns():
    assert policy_action(Situation.INCOMPLETE_OR_IMPLAUSIBLE) == RETURN
    assert policy_action(premium_situation(plausible=False)) == RETURN
    assert policy_action(completeness_situation()) == RETURN


def test_row_compliance_or_conflict_escalates():
    assert policy_action(Situation.COMPLIANCE_OR_CONFLICT) == ESCALATE
    assert policy_action(compliance_situation()) == ESCALATE


def test_meal_situation_short_meal_is_a_data_problem(p):
    call = 7.0
    short = calc.tenths((p.meal.min_duration_minutes - 6) / 60)
    facts = calc.meal_facts(call, 12.0, calc.tenths(12.0 + short), p)
    assert facts.is_short and not facts.is_late
    assert meal_situation(facts, plausible=True) is Situation.INCOMPLETE_OR_IMPLAUSIBLE


def test_meal_situation_late_meal_plausible_is_premium(p):
    call = 7.0
    meal_out = calc.tenths(call + p.meal.deadline_hours + 0.5)
    facts = calc.meal_facts(call, meal_out, calc.tenths(meal_out + 0.5), p)
    assert facts.is_late and not facts.is_short
    assert meal_situation(facts, plausible=True) is Situation.PREMIUM_COMPLETE_PLAUSIBLE
    assert meal_situation(facts, plausible=False) is Situation.INCOMPLETE_OR_IMPLAUSIBLE


def test_day_is_plausible_uses_the_yaml_limit(p):
    unit = p.payroll.time_unit_hours
    limit = p.plausibility.max_day_hours
    assert day_is_plausible(_day(5.0, 10.0, 10.5, calc.tenths(5.0 + limit)), p)
    assert not day_is_plausible(_day(5.0, 10.0, 10.5, calc.tenths(5.0 + limit + unit)), p)
    assert not day_is_plausible(_day(5.0, 10.0, 10.5, None), p)
    assert not day_is_plausible(_day(5.0, 10.5, 10.0, 15.0), p)


def test_combined_action_most_severe_wins():
    assert combined_action([]) == NONE
    assert combined_action([APPROVE]) == APPROVE
    assert combined_action([APPROVE, RETURN]) == RETURN
    assert combined_action([RETURN, ESCALATE, APPROVE]) == ESCALATE
    with pytest.raises(ValueError):
        combined_action(["ship"])


def test_severity_order_matches_adr():
    assert policy.SEVERITY[ESCALATE] > policy.SEVERITY[RETURN] > policy.SEVERITY[APPROVE]
