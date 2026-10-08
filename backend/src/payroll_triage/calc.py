"""Pure arithmetic over timecard events, parameterized by the rule parameters.

These helpers are the only place where domain arithmetic lives. The data
generator uses them to compute expectations by construction (Iteration 1) and
the rule engine will use the same functions for detection (Iteration 2), so
the ground truth and the engine cannot disagree on arithmetic (ADR-007,
ADR-008).

Times are decimal hours from midnight of the shift date, in tenths. Money is
Decimal with two places.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from payroll_triage.params import RuleParameters

TENTH = Decimal("0.1")
CENT = Decimal("0.01")


def tenths(value: float) -> float:
    """Round a time or duration to one decimal (tenths of an hour)."""
    return float(Decimal(str(value)).quantize(TENTH, rounding=ROUND_HALF_UP))


def minutes(hours: float) -> int:
    """Whole minutes in a duration expressed in hours (tenths resolve exactly)."""
    return int(round(hours * 60))


def money(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


# ---------- meal ----------


@dataclass(frozen=True)
class MealFacts:
    hours_to_meal: float
    meal_minutes: int
    minutes_late: int
    increments: int
    penalty_usd: Decimal
    is_late: bool
    is_short: bool


def meal_penalty_increments(minutes_late: int, params: RuleParameters) -> int:
    if minutes_late <= 0:
        return 0
    return math.ceil(minutes_late / params.meal.penalty_increment_minutes)


def meal_penalty_amount(increments: int, params: RuleParameters) -> Decimal:
    schedule = params.meal.penalty_schedule_usd
    total = Decimal("0.00")
    for i in range(increments):
        total += schedule[min(i, len(schedule) - 1)]
    return money(total)


def meal_facts(call: float, meal_out: float, meal_in: float, params: RuleParameters) -> MealFacts:
    hours_to_meal = tenths(meal_out - call)
    meal_minutes = minutes(tenths(meal_in - meal_out))
    minutes_late = max(0, minutes(hours_to_meal - params.meal.deadline_hours))
    increments = meal_penalty_increments(minutes_late, params)
    return MealFacts(
        hours_to_meal=hours_to_meal,
        meal_minutes=meal_minutes,
        minutes_late=minutes_late,
        increments=increments,
        penalty_usd=meal_penalty_amount(increments, params),
        is_late=minutes_late > 0,
        is_short=meal_minutes < params.meal.min_duration_minutes,
    )


# ---------- hours worked and extended day ----------


def meal_is_deductible(meal_out: float, meal_in: float, params: RuleParameters) -> bool:
    return minutes(tenths(meal_in - meal_out)) >= params.meal.min_duration_minutes


def hours_worked(
    call: float, meal_out: float, meal_in: float, wrap: float, params: RuleParameters
) -> float:
    elapsed = tenths(wrap - call)
    if meal_is_deductible(meal_out, meal_in, params):
        return tenths(elapsed - (meal_in - meal_out))
    return elapsed


@dataclass(frozen=True)
class DayHoursFacts:
    elapsed_hours: float
    hours_worked: float
    hours_over_threshold: float
    extended_multiplier: float
    daily_overtime_hours: float


def day_hours_facts(
    call: float, meal_out: float, meal_in: float, wrap: float, params: RuleParameters
) -> DayHoursFacts:
    worked = hours_worked(call, meal_out, meal_in, wrap, params)
    over = tenths(max(0.0, worked - params.extended_day.threshold_hours))
    capped = min(worked, params.extended_day.threshold_hours)
    daily_ot = tenths(max(0.0, capped - params.overtime.daily_after_hours))
    return DayHoursFacts(
        elapsed_hours=tenths(wrap - call),
        hours_worked=worked,
        hours_over_threshold=over,
        extended_multiplier=params.extended_day.multiplier,
        daily_overtime_hours=daily_ot,
    )


def premium_amount(hours: float, hourly_rate: Decimal, multiplier: float) -> Decimal:
    """Premium line amount for `hours` at rate x multiplier (the full rate for those hours)."""
    return money(Decimal(str(hours)) * hourly_rate * Decimal(str(multiplier)))


# ---------- rest ----------


@dataclass(frozen=True)
class RestFacts:
    rest_hours: float
    invaded_hours: float
    invasion_multiplier: float
    is_invaded: bool


def rest_facts(prev_wrap: float, next_call: float, params: RuleParameters) -> RestFacts:
    rest = tenths(next_call + 24.0 - prev_wrap)
    invaded = tenths(max(0.0, params.rest.min_hours - rest))
    return RestFacts(
        rest_hours=rest,
        invaded_hours=invaded,
        invasion_multiplier=params.rest.invasion_multiplier,
        is_invaded=invaded > 0,
    )


# ---------- weekly overtime (calculation only, ADR-010) ----------


def weekly_overtime_hours(daily_hours_worked: Iterable[float], params: RuleParameters) -> float:
    total = tenths(sum(daily_hours_worked))
    return tenths(max(0.0, total - params.overtime.weekly_after_hours))


# ---------- business days and eligibility ----------


def is_business_day(day: dt.date, holidays: Iterable[dt.date] = ()) -> bool:
    return day.weekday() < 5 and day not in set(holidays)


def add_business_days(start: dt.date, n: int, holidays: Iterable[dt.date] = ()) -> dt.date:
    """The date n business days after `start` (start itself is not counted)."""
    hol = set(holidays)
    day = start
    remaining = n
    while remaining > 0:
        day += dt.timedelta(days=1)
        if is_business_day(day, hol):
            remaining -= 1
    return day


def business_days_between(after: dt.date, until: dt.date, holidays: Iterable[dt.date] = ()) -> int:
    """Business days strictly after `after` up to and including `until` (0 if until <= after)."""
    if until <= after:
        return 0
    hol = set(holidays)
    count = 0
    day = after
    while day < until:
        day += dt.timedelta(days=1)
        if is_business_day(day, hol):
            count += 1
    return count


@dataclass(frozen=True)
class EligibilityFacts:
    first_day_of_work: dt.date
    deadline_date: dt.date
    completed_on: dt.date | None
    as_of: dt.date
    is_overdue: bool
    business_days_overdue: int


def eligibility_facts(
    first_day_of_work: dt.date,
    completed_on: dt.date | None,
    as_of: dt.date,
    params: RuleParameters,
    holidays: Iterable[dt.date] = (),
) -> EligibilityFacts:
    deadline = add_business_days(
        first_day_of_work, params.eligibility.deadline_business_days, holidays
    )
    if completed_on is None:
        overdue = as_of > deadline
        days_over = business_days_between(deadline, as_of, holidays)
    else:
        overdue = completed_on > deadline
        days_over = business_days_between(deadline, completed_on, holidays)
    return EligibilityFacts(
        first_day_of_work=first_day_of_work,
        deadline_date=deadline,
        completed_on=completed_on,
        as_of=as_of,
        is_overdue=overdue,
        business_days_overdue=days_over if overdue else 0,
    )
