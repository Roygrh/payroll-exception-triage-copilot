"""Shared timecard model: completeness, the no-meal-day exception and round trips."""

from __future__ import annotations

import datetime as dt

import pytest

from payroll_triage.calc import tenths
from payroll_triage.corpus.deal_memos import load_deal_memos
from payroll_triage.data.generator import load_generated_timecards
from payroll_triage.evals.expectations import completeness_findings, meal_findings
from payroll_triage.params import load_parameters
from payroll_triage.timecards import Timecard, TimecardDay


@pytest.fixture(scope="module")
def p():
    return load_parameters()


def _day(call, meal_out, meal_in, wrap, date=dt.date(2026, 3, 10)) -> TimecardDay:
    return TimecardDay(
        date=date,
        weekday=date.strftime("%a"),
        day_type="1-Work",
        work_location="S-Stage",
        call=call,
        meal_out=meal_out,
        meal_in=meal_in,
        wrap=wrap,
    )


def _tc(days) -> Timecard:
    memo = load_deal_memos()["DM-01"]
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


def test_completeness_and_chronology():
    assert _day(7.0, 12.0, 12.5, 15.5).is_chronological()
    assert not _day(7.0, 12.5, 12.0, 15.5).is_chronological()
    assert _day(7.0, None, 12.5, 15.5).missing_entries() == ["meal_out"]
    assert not _day(7.0, None, 12.5, 15.5).is_complete()


def test_no_meal_day_dismissed_before_deadline_raises_nothing(p):
    call = 7.0
    wrap = tenths(call + p.meal.deadline_hours)  # dismissed exactly at the deadline
    day = _day(call, wrap, wrap, wrap)
    assert day.is_no_meal_day(p)
    tc = _tc([day])
    assert completeness_findings(tc, p) == []
    assert meal_findings(tc, p) == []


def test_no_meal_day_past_deadline_is_not_the_exception(p):
    call = 7.0
    wrap = tenths(call + p.meal.deadline_hours + p.payroll.time_unit_hours)
    day = _day(call, wrap, wrap, wrap)
    assert not day.is_no_meal_day(p)
    found = meal_findings(_tc([day]), p)
    assert len(found) == 1 and found[0].policy_action == "return"


def test_equal_meal_entries_before_wrap_is_a_short_meal(p):
    day = _day(7.0, 12.0, 12.0, 15.5)
    assert not day.is_no_meal_day(p)
    found = meal_findings(_tc([day]), p)
    assert len(found) == 1 and found[0].facts["is_short"] is True


def test_round_trip_through_dict():
    tc = _tc([_day(7.0, 12.0, 12.5, 15.5), _day(7.0, None, 12.5, 15.5, dt.date(2026, 3, 11))])
    again = Timecard.from_dict(tc.to_dict())
    assert again == tc


def test_generated_file_loads_as_timecards():
    cards = load_generated_timecards()
    assert len(cards) == 22
    assert all(isinstance(c, Timecard) for c in cards)
    assert {c.scenario_id for c in cards} >= {"SC-03", "SC-05", "SC-F01"}
