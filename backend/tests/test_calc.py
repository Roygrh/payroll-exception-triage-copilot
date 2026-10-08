"""Tests for the arithmetic helpers, parameterized from the YAML (no literal domain numbers)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from payroll_triage import calc
from payroll_triage.params import load_parameters


@pytest.fixture(scope="module")
def p():
    return load_parameters()


def test_tenths_and_minutes():
    assert calc.tenths(6.4999) == 6.5
    assert calc.minutes(0.4) == 24
    assert calc.minutes(0.5) == 30


def test_meal_on_time_has_no_penalty(p):
    call = 7.0
    out = call + p.meal.deadline_hours
    f = calc.meal_facts(call, out, out + 0.5, p)
    assert not f.is_late and f.increments == 0 and f.penalty_usd == Decimal("0.00")
    assert not f.is_short


def test_meal_one_increment(p):
    call = 7.0
    out = call + p.meal.deadline_hours + p.meal.penalty_increment_minutes / 60
    f = calc.meal_facts(call, out, out + 0.5, p)
    assert f.is_late and f.increments == 1
    assert f.penalty_usd == p.meal.penalty_schedule_usd[0]


def test_meal_started_increment_counts_whole(p):
    call = 7.0
    out = call + p.meal.deadline_hours + 0.1  # six minutes late
    f = calc.meal_facts(call, out, out + 0.5, p)
    assert f.minutes_late == 6 and f.increments == 1


def test_meal_schedule_repeats_last_value(p):
    sched = p.meal.penalty_schedule_usd
    n = len(sched) + 2
    expected = sum(sched) + sched[-1] * 2
    assert calc.meal_penalty_amount(n, p) == calc.money(expected)


def test_short_meal_flag_and_not_deducted(p):
    short_hours = calc.tenths((p.meal.min_duration_minutes - 6) / 60)
    f = calc.meal_facts(7.0, 12.0, 12.0 + short_hours, p)
    assert f.is_short and not f.is_late
    assert not calc.meal_is_deductible(12.0, 12.0 + short_hours, p)
    assert calc.hours_worked(7.0, 12.0, 12.0 + short_hours, 15.5, p) == 8.5


def test_hours_worked_deducts_qualifying_meal(p):
    assert calc.hours_worked(7.0, 12.0, 12.5, 15.5, p) == 8.0


def test_extended_day_facts(p):
    t = p.extended_day.threshold_hours
    call = 6.0
    wrap = call + 0.5 + t + 1.5
    f = calc.day_hours_facts(call, 11.5, 12.0, wrap, p)
    assert f.hours_worked == calc.tenths(t + 1.5)
    assert f.hours_over_threshold == 1.5
    assert f.daily_overtime_hours == calc.tenths(t - p.overtime.daily_after_hours)
    assert f.extended_multiplier == p.extended_day.multiplier


def test_day_at_threshold_is_not_extended(p):
    t = p.extended_day.threshold_hours
    f = calc.day_hours_facts(6.0, 11.5, 12.0, 6.0 + 0.5 + t, p)
    assert f.hours_over_threshold == 0.0


def test_rest_facts(p):
    f = calc.rest_facts(prev_wrap=20.0, next_call=4.5, params=p)
    assert f.rest_hours == 8.5
    assert f.invaded_hours == calc.tenths(p.rest.min_hours - 8.5)
    assert f.is_invaded
    g = calc.rest_facts(prev_wrap=25.0, next_call=10.5, params=p)
    assert g.rest_hours == 9.5
    h = calc.rest_facts(prev_wrap=15.5, next_call=7.0, params=p)
    assert not h.is_invaded and h.invaded_hours == 0.0


def test_premium_amount_rounds_to_cents():
    assert calc.premium_amount(1.5, Decimal("10.01"), 2.0) == Decimal("30.03")
    assert calc.premium_amount(0.1, Decimal("10.01"), 1.5) == Decimal(
        "1.50"
    )  # 1.5015 rounds half up


def test_weekly_overtime(p):
    w = p.overtime.weekly_after_hours
    assert calc.weekly_overtime_hours([w / 5] * 5, p) == 0.0
    assert calc.weekly_overtime_hours([w / 5 + 1.0] * 5, p) == 5.0


def test_business_days():
    mon = dt.date(2026, 3, 2)
    assert calc.add_business_days(mon, 3) == dt.date(2026, 3, 5)
    fri = dt.date(2026, 3, 6)
    assert calc.add_business_days(fri, 3) == dt.date(2026, 3, 11)
    assert calc.business_days_between(dt.date(2026, 3, 5), dt.date(2026, 3, 16)) == 7
    assert calc.business_days_between(dt.date(2026, 3, 5), dt.date(2026, 3, 5)) == 0
    holiday = dt.date(2026, 3, 3)
    assert calc.add_business_days(mon, 3, holidays=[holiday]) == dt.date(2026, 3, 6)


def test_eligibility_facts(p):
    n = p.eligibility.deadline_business_days
    start = dt.date(2026, 3, 2)
    deadline = calc.add_business_days(start, n)
    pending = calc.eligibility_facts(start, None, dt.date(2026, 3, 16), p)
    assert pending.is_overdue and pending.deadline_date == deadline
    assert pending.business_days_overdue == calc.business_days_between(
        deadline, dt.date(2026, 3, 16)
    )
    on_time = calc.eligibility_facts(start, deadline, dt.date(2026, 3, 16), p)
    assert not on_time.is_overdue and on_time.business_days_overdue == 0
    late_done = calc.eligibility_facts(
        start, deadline + dt.timedelta(days=1), dt.date(2026, 3, 16), p
    )
    assert late_done.is_overdue and late_done.business_days_overdue >= 1
    not_yet = calc.eligibility_facts(start, None, deadline, p)
    assert not not_yet.is_overdue
