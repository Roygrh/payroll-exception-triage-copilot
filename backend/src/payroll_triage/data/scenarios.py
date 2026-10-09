"""Scenario catalog loader (data/scenarios.yaml)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from payroll_triage.paths import scenarios_path
from payroll_triage.policy import ACTIONS as _ACTIONS
from payroll_triage.policy import SEVERITY as _SEVERITY
from payroll_triage.timecards import TIME_FIELDS as _TIME_FIELDS

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")
DAY_KINDS = {
    "clean",
    "long_day",
    "late_meal",
    "short_meal",
    "missing",
    "wrap_before_call",
    "explicit",
}
# Re-exported for callers of the catalog; the definitions live in the shared modules.
TIME_FIELDS = _TIME_FIELDS
ACTIONS = _ACTIONS
SEVERITY = _SEVERITY


class ScenarioError(ValueError):
    pass


@dataclass(frozen=True)
class DaySpec:
    kind: str
    hours_worked: float | None = None
    hours_to_meal: float | None = None
    meal_minutes: int | None = None
    field: str | None = None
    call: float | None = None
    meal_out: float | None = None
    meal_in: float | None = None
    wrap: float | None = None


@dataclass(frozen=True)
class Scenario:
    id: str
    deal_memo: str
    week_ending: dt.date
    category: str
    description: str
    expected_rules: tuple[str, ...]
    expected_action: str
    days: dict[str, DaySpec] = field(default_factory=dict)


@dataclass(frozen=True)
class FillerSpec:
    id: str
    employee_id: str
    employee_name: str
    occupation_code: str
    department: str
    start_date: dt.date


@dataclass(frozen=True)
class CleanDay:
    call: float
    meal_out: float
    meal_in: float
    wrap: float


@dataclass(frozen=True)
class FillerJitter:
    call: tuple[float, ...]
    meal_after: tuple[float, ...]
    after_meal: tuple[float, ...]


@dataclass(frozen=True)
class Catalog:
    seed: int
    as_of_date: dt.date
    payroll_run_date: dt.date
    demo_week_ending: dt.date
    queue_status: str
    demo_approver: str
    holidays: tuple[dt.date, ...]
    production: dict[str, Any]
    labels: dict[str, dict[str, str]]
    clean_day: CleanDay
    long_day_call: float
    long_day_meal_before_deadline: float
    long_day_meal_duration: float
    late_meal_duration: float
    late_meal_after_hours: float
    wrap_before_call_wrap: float
    filler_jitter: FillerJitter
    filler_location: dict[str, str]
    scenarios: tuple[Scenario, ...]
    filler: tuple[FillerSpec, ...]

    def scenario(self, scenario_id: str) -> Scenario:
        for s in self.scenarios:
            if s.id == scenario_id:
                return s
        raise ScenarioError(f"unknown scenario {scenario_id}")


def _date(value: Any) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def _parse_day(scenario_id: str, weekday: str, raw: dict[str, Any]) -> DaySpec:
    kind = raw.get("kind")
    if kind not in DAY_KINDS:
        raise ScenarioError(f"{scenario_id} {weekday}: unknown day kind {kind!r}")
    spec = DaySpec(
        kind=kind,
        hours_worked=raw.get("hours_worked"),
        hours_to_meal=raw.get("hours_to_meal"),
        meal_minutes=raw.get("meal_minutes"),
        field=raw.get("field"),
        call=raw.get("call"),
        meal_out=raw.get("meal_out"),
        meal_in=raw.get("meal_in"),
        wrap=raw.get("wrap"),
    )
    required = {
        "long_day": ("hours_worked",),
        "late_meal": ("hours_to_meal",),
        "short_meal": ("meal_minutes",),
        "missing": ("field",),
        "explicit": TIME_FIELDS,
    }.get(kind, ())
    for name in required:
        if getattr(spec, name) is None:
            raise ScenarioError(f"{scenario_id} {weekday}: {kind} needs {name}")
    if kind == "missing" and spec.field not in TIME_FIELDS:
        raise ScenarioError(f"{scenario_id} {weekday}: missing.field must be one of {TIME_FIELDS}")
    return spec


def _parse_scenario(raw: dict[str, Any]) -> Scenario:
    sid = raw["id"]
    expected = raw.get("expected") or {}
    action = expected.get("action", "none")
    if action not in ACTIONS:
        raise ScenarioError(f"{sid}: invalid expected action {action!r}")
    days_raw = raw.get("days") or {}
    days: dict[str, DaySpec] = {}
    for weekday, d in days_raw.items():
        if weekday not in WEEKDAYS:
            raise ScenarioError(f"{sid}: day key {weekday!r} must be one of {WEEKDAYS}")
        days[weekday] = _parse_day(sid, weekday, d)
    return Scenario(
        id=sid,
        deal_memo=raw["deal_memo"],
        week_ending=_date(raw["week_ending"]),
        category=raw["category"],
        description=raw["description"],
        expected_rules=tuple(expected.get("rules") or ()),
        expected_action=action,
        days=days,
    )


def parse_catalog(raw: dict[str, Any]) -> Catalog:
    clean = raw["clean_day"]
    catalog = Catalog(
        seed=int(raw["seed"]),
        as_of_date=_date(raw["as_of_date"]),
        payroll_run_date=_date(raw["payroll_run_date"]),
        demo_week_ending=_date(raw["demo_week_ending"]),
        queue_status=raw["queue_status"],
        demo_approver=str(raw["demo_approver"]),
        holidays=tuple(_date(h) for h in raw.get("holidays") or ()),
        production=dict(raw["production"]),
        labels={k: dict(v) for k, v in raw["labels"].items()},
        clean_day=CleanDay(**{k: float(clean[k]) for k in TIME_FIELDS}),
        long_day_call=float(raw["long_day_call"]),
        long_day_meal_before_deadline=float(raw["long_day_meal_before_deadline"]),
        long_day_meal_duration=float(raw["long_day_meal_duration"]),
        late_meal_duration=float(raw["late_meal_duration"]),
        late_meal_after_hours=float(raw["late_meal_after_hours"]),
        wrap_before_call_wrap=float(raw["wrap_before_call_wrap"]),
        filler_jitter=FillerJitter(
            call=tuple(float(v) for v in raw["filler_jitter"]["call"]),
            meal_after=tuple(float(v) for v in raw["filler_jitter"]["meal_after"]),
            after_meal=tuple(float(v) for v in raw["filler_jitter"]["after_meal"]),
        ),
        filler_location=dict(raw["filler_location"]),
        scenarios=tuple(_parse_scenario(s) for s in raw["scenarios"]),
        filler=tuple(
            FillerSpec(
                id=f["id"],
                employee_id=f["employee"]["id"],
                employee_name=f["employee"]["name"],
                occupation_code=str(f["occupation_code"]),
                department=f["department"],
                start_date=_date(f["start_date"]),
            )
            for f in raw.get("filler") or ()
        ),
    )
    if "work" not in catalog.labels.get("day_type", {}):
        raise ScenarioError("labels.day_type.work is required")
    if "stage" not in catalog.labels.get("work_location", {}):
        raise ScenarioError("labels.work_location.stage is required")
    after = catalog.labels.get("timecard_status_after", {})
    if set(after) != {"approve", "return"}:
        raise ScenarioError("labels.timecard_status_after must map approve and return")
    for key in ("hire_state", "hire_city", "work_state", "primary_work_city"):
        if key not in catalog.filler_location:
            raise ScenarioError(f"filler_location.{key} is required")
    for name in ("call", "meal_after", "after_meal"):
        if not getattr(catalog.filler_jitter, name):
            raise ScenarioError(f"filler_jitter.{name} must not be empty")
    ids = [s.id for s in catalog.scenarios] + [f.id for f in catalog.filler]
    if len(ids) != len(set(ids)):
        raise ScenarioError("duplicate scenario ids")
    for s in catalog.scenarios:
        if s.week_ending.weekday() != 5:
            raise ScenarioError(f"{s.id}: week_ending {s.week_ending} is not a Saturday")
        if s.expected_rules and s.expected_action == "none":
            raise ScenarioError(f"{s.id}: expected rules but action none")
        if not s.expected_rules and s.expected_action != "none":
            raise ScenarioError(f"{s.id}: expected action without rules")
    return catalog


def load_catalog(path: Path | None = None) -> Catalog:
    path = path or scenarios_path()
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ScenarioError(f"{path}: expected a mapping")
    return parse_catalog(raw)
