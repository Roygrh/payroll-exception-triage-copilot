"""Shared timecard model (domain model, section 6).

Used by the generator (Iteration 1), the expectation oracle, the rule engine
and the persistence layer so that all of them agree on what a day and a
timecard are. Times are decimal hours from midnight of the shift date, in
tenths; a value above 24.0 is the next calendar day.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from typing import Any

from payroll_triage.calc import tenths
from payroll_triage.params import RuleParameters

TIME_FIELDS = ("call", "meal_out", "meal_in", "wrap")
DEFAULT_WORK_DAY_TYPE = "1-Work"


@dataclass(frozen=True)
class TimecardDay:
    date: dt.date
    weekday: str
    day_type: str
    work_location: str
    call: float | None
    meal_out: float | None
    meal_in: float | None
    wrap: float | None

    def is_complete(self) -> bool:
        return all(getattr(self, f) is not None for f in TIME_FIELDS)

    def is_chronological(self) -> bool:
        if not self.is_complete():
            return False
        return self.call <= self.meal_out <= self.meal_in <= self.wrap  # type: ignore[operator]

    def missing_entries(self) -> list[str]:
        return [f for f in TIME_FIELDS if getattr(self, f) is None]

    def is_no_meal_day(self, params: RuleParameters) -> bool:
        """Dismissed before the meal deadline with no meal taken (agreement 7.4 and 8.7).

        Recorded as meal out = meal in = wrap on a day whose elapsed time does not exceed the
        meal deadline. Such a day is complete, is not a short meal and owes no penalty.
        """
        if not self.is_chronological():
            return False
        assert self.call is not None and self.wrap is not None
        if not (self.meal_out == self.meal_in == self.wrap):
            return False
        return tenths(self.wrap - self.call) <= params.meal.deadline_hours

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["date"] = self.date.isoformat()
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TimecardDay:
        return cls(
            date=_date(raw["date"]),
            weekday=raw["weekday"],
            day_type=raw["day_type"],
            work_location=raw["work_location"],
            call=_time(raw.get("call")),
            meal_out=_time(raw.get("meal_out")),
            meal_in=_time(raw.get("meal_in")),
            wrap=_time(raw.get("wrap")),
        )


@dataclass(frozen=True)
class Timecard:
    id: str
    scenario_id: str
    employee_id: str
    employee_name: str
    deal_memo_id: str
    occupation_code: str
    department: str
    week_ending: dt.date
    producer_week: dt.date
    status: str
    days: tuple[TimecardDay, ...]

    def work_days(self, work_day_type: str = DEFAULT_WORK_DAY_TYPE) -> list[TimecardDay]:
        """Only work days are evaluated by the rules (domain model, section 6)."""
        return [d for d in self.days if d.day_type == work_day_type]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["week_ending"] = self.week_ending.isoformat()
        data["producer_week"] = self.producer_week.isoformat()
        data["days"] = [d.to_dict() for d in self.days]
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Timecard:
        return cls(
            id=raw["id"],
            scenario_id=raw.get("scenario_id", ""),
            employee_id=raw["employee_id"],
            employee_name=raw["employee_name"],
            deal_memo_id=raw["deal_memo_id"],
            occupation_code=str(raw["occupation_code"]),
            department=raw["department"],
            week_ending=_date(raw["week_ending"]),
            producer_week=_date(raw["producer_week"]),
            status=raw["status"],
            days=tuple(TimecardDay.from_dict(d) for d in raw["days"]),
        )


def _date(value: Any) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def _time(value: Any) -> float | None:
    return None if value is None else float(value)
