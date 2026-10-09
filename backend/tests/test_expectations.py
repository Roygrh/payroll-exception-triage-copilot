"""Policy branches of the expectation oracle (ADR-009 rows the engine must reproduce)."""

from __future__ import annotations

import datetime as dt

import pytest

from payroll_triage.calc import tenths
from payroll_triage.corpus.deal_memos import load_deal_memos
from payroll_triage.evals.expectations import (
    combined_action,
    completeness_findings,
    expected_findings,
    extended_day_findings,
    meal_findings,
    rest_findings,
)
from payroll_triage.params import load_parameters
from payroll_triage.timecards import Timecard, TimecardDay

WORK = "1-Work"


@pytest.fixture(scope="module")
def p():
    return load_parameters()


@pytest.fixture(scope="module")
def memo():
    return load_deal_memos()["DM-01"]


def _day(date: dt.date, call, meal_out, meal_in, wrap, day_type=WORK) -> TimecardDay:
    return TimecardDay(
        date=date,
        weekday=date.strftime("%a"),
        day_type=day_type,
        work_location="S-Stage",
        call=call,
        meal_out=meal_out,
        meal_in=meal_in,
        wrap=wrap,
    )


def _tc(days: list[TimecardDay], memo) -> Timecard:
    return Timecard(
        id="TC-TEST",
        scenario_id="SC-TEST",
        employee_id=memo.employee_id,
        employee_name=memo.employee_name,
        deal_memo_id=memo.id,
        occupation_code=memo.occupation_code,
        department=memo.department,
        week_ending=dt.date(2026, 3, 14),
        producer_week=dt.date(2026, 3, 8),
        status="Ready for approver 1",
        days=tuple(days),
    )


D1 = dt.date(2026, 3, 9)
D2 = dt.date(2026, 3, 10)


def test_late_meal_on_implausible_day_is_returned(p, memo):
    unit = p.payroll.time_unit_hours
    call = 5.0
    wrap = tenths(call + p.plausibility.max_day_hours + unit)  # one unit above the limit
    meal_out = tenths(call + p.meal.deadline_hours + unit)
    tc = _tc([_day(D1, call, meal_out, tenths(meal_out + 0.5), wrap)], memo)
    meal = meal_findings(tc, p)
    assert len(meal) == 1 and meal[0].policy_action == "return"
    ext = extended_day_findings(tc, memo, p)
    assert len(ext) == 1 and ext[0].policy_action == "return"


def test_day_exactly_at_plausibility_limit_is_plausible(p, memo):
    call = 5.0
    wrap = tenths(call + p.plausibility.max_day_hours)
    meal_out = tenths(call + p.meal.deadline_hours - 0.5)
    tc = _tc([_day(D1, call, meal_out, tenths(meal_out + 0.5), wrap)], memo)
    ext = extended_day_findings(tc, memo, p)
    assert len(ext) == 1 and ext[0].policy_action == "approve"


def test_late_and_short_meal_same_day_returns(p, memo):
    call = 7.0
    meal_out = tenths(call + p.meal.deadline_hours + 0.5)
    short = tenths((p.meal.min_duration_minutes - 6) / 60)
    tc = _tc([_day(D1, call, meal_out, tenths(meal_out + short), tenths(meal_out + 4.0))], memo)
    meal = meal_findings(tc, p)
    assert len(meal) == 1
    assert meal[0].facts["is_late"] is True and meal[0].facts["is_short"] is True
    assert meal[0].policy_action == "return"


def test_rest_invasion_with_incomplete_next_day(p, memo):
    prev = _day(D1, 11.0, 16.0, 16.5, 20.0)
    nxt = _day(D2, 4.5, 9.5, None, 13.0)
    tc = _tc([prev, nxt], memo)
    rest = rest_findings(tc, memo, p)
    assert len(rest) == 1 and rest[0].policy_action == "return"
    comp = completeness_findings(tc, p)
    assert len(comp) == 1 and comp[0].facts["missing_entries"] == ["meal_in"]
    assert combined_action(rest + comp) == "return"


def test_rest_not_evaluated_when_previous_wrap_missing(p, memo):
    prev = _day(D1, 11.0, 16.0, 16.5, None)
    nxt = _day(D2, 4.5, 9.5, 10.0, 13.0)
    assert rest_findings(_tc([prev, nxt], memo), memo, p) == []


def test_non_work_days_are_skipped(p, memo):
    travel = _day(D1, 7.0, 13.5, 14.0, 17.0, day_type="2-Travel")  # would be a late meal
    tc = _tc([travel], memo)
    assert expected_findings(tc, memo, p, dt.date(2026, 3, 16)) == []
    assert expected_findings(tc, memo, p, dt.date(2026, 3, 16), work_day_type="2-Travel") != []


def test_out_of_order_entries_return(p, memo):
    tc = _tc([_day(D1, 7.0, 12.5, 12.0, 15.5)], memo)  # meal in before meal out
    comp = completeness_findings(tc, p)
    assert len(comp) == 1 and comp[0].facts["entries_out_of_order"] is True
    assert meal_findings(tc, p) == [] and extended_day_findings(tc, memo, p) == []


def test_combined_action_order():
    class F:
        def __init__(self, a):
            self.policy_action = a

    assert combined_action([]) == "none"
    assert combined_action([F("approve")]) == "approve"
    assert combined_action([F("approve"), F("return")]) == "return"
    assert combined_action([F("return"), F("escalate"), F("approve")]) == "escalate"
