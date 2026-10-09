"""Seeded timecard generator (P1.I1.S5).

Builds one timecard per scenario from data/scenarios.yaml, plus clean timecards
for the filler crew, and writes them to data/generated/. Scenario days are built
by construction from the day specs; only the filler crew uses the seeded random
generator (for small, realistic jitter), so the same seed yields identical files.
"""

from __future__ import annotations

import datetime as dt
import json
import random
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from payroll_triage.calc import tenths
from payroll_triage.corpus.deal_memos import DealMemo, load_deal_memos, parse_deal_memo
from payroll_triage.data.scenarios import (
    WEEKDAYS,
    Catalog,
    DaySpec,
    FillerSpec,
    Scenario,
    load_catalog,
)
from payroll_triage.params import RuleParameters, get_parameters
from payroll_triage.paths import generated_dir
from payroll_triage.timecards import Timecard, TimecardDay

TIMECARDS_FILE = "timecards.json"
FILLER_MEMOS_FILE = "filler-deal-memos.json"


@dataclass(frozen=True)
class GeneratedData:
    seed: int
    as_of_date: dt.date
    timecards: tuple[Timecard, ...]
    filler_deal_memos: tuple[DealMemo, ...]


# ---------- day construction ----------


def _week_dates(week_ending: dt.date) -> dict[str, dt.date]:
    monday = week_ending - dt.timedelta(days=5)
    return {wd: monday + dt.timedelta(days=i) for i, wd in enumerate(WEEKDAYS)}


def _check_unit(label: str, value: float, params: RuleParameters, *, minutes: bool = False) -> None:
    """Scenario inputs must be representable in the timecard recording unit."""
    unit = params.payroll.time_unit_hours * (60 if minutes else 1)
    ratio = value / unit
    if abs(ratio - round(ratio)) > 1e-9:
        raise ValueError(f"{label}={value} is not a multiple of the time unit ({unit})")


def build_day(
    spec: DaySpec, date: dt.date, weekday: str, catalog: Catalog, params: RuleParameters
) -> TimecardDay:
    c = catalog.clean_day
    call, meal_out, meal_in, wrap = c.call, c.meal_out, c.meal_in, c.wrap
    if spec.kind == "clean":
        pass
    elif spec.kind == "long_day":
        _check_unit("hours_worked", spec.hours_worked, params)  # type: ignore[arg-type]
        call = catalog.long_day_call
        meal_out = tenths(call + params.meal.deadline_hours - catalog.long_day_meal_before_deadline)
        meal_in = tenths(meal_out + catalog.long_day_meal_duration)
        wrap = tenths(call + catalog.long_day_meal_duration + spec.hours_worked)  # type: ignore[operator]
    elif spec.kind == "late_meal":
        _check_unit("hours_to_meal", spec.hours_to_meal, params)  # type: ignore[arg-type]
        meal_out = tenths(call + spec.hours_to_meal)  # type: ignore[operator]
        meal_in = tenths(meal_out + catalog.late_meal_duration)
        wrap = tenths(meal_in + catalog.late_meal_after_hours)
    elif spec.kind == "short_meal":
        _check_unit("meal_minutes", spec.meal_minutes, params, minutes=True)  # type: ignore[arg-type]
        meal_in = tenths(meal_out + spec.meal_minutes / 60)  # type: ignore[operator]
    elif spec.kind == "wrap_before_call":
        wrap = catalog.wrap_before_call_wrap
    elif spec.kind == "explicit":
        call, meal_out, meal_in, wrap = spec.call, spec.meal_out, spec.meal_in, spec.wrap  # type: ignore[assignment]
    values: dict[str, float | None] = {
        "call": call,
        "meal_out": meal_out,
        "meal_in": meal_in,
        "wrap": wrap,
    }
    if spec.kind == "missing":
        values[spec.field] = None  # type: ignore[index]
    return TimecardDay(
        date=date,
        weekday=weekday,
        day_type=catalog.labels["day_type"]["work"],
        work_location=catalog.labels["work_location"]["stage"],
        **values,  # type: ignore[arg-type]
    )


def _timecard_id(employee_id: str, week_ending: dt.date) -> str:
    return f"TC-{employee_id}-{week_ending:%Y%m%d}"


def build_scenario_timecard(
    scenario: Scenario, memo: DealMemo, catalog: Catalog, params: RuleParameters
) -> Timecard:
    dates = _week_dates(scenario.week_ending)
    if dates["Mon"] < memo.start_date:
        raise ValueError(
            f"{scenario.id}: first work day {dates['Mon']} precedes {memo.id} start "
            f"{memo.start_date}"
        )
    days = tuple(
        build_day(scenario.days.get(wd, DaySpec(kind="clean")), dates[wd], wd, catalog, params)
        for wd in WEEKDAYS
    )
    return Timecard(
        id=_timecard_id(memo.employee_id, scenario.week_ending),
        scenario_id=scenario.id,
        employee_id=memo.employee_id,
        employee_name=memo.employee_name,
        deal_memo_id=memo.id,
        occupation_code=memo.occupation_code,
        department=memo.department,
        week_ending=scenario.week_ending,
        producer_week=scenario.week_ending - dt.timedelta(days=6),
        status=catalog.queue_status,
        days=days,
    )


# ---------- filler crew ----------


def _filler_memo(spec: FillerSpec, catalog: Catalog, params: RuleParameters) -> DealMemo:
    scale = params.scale_for(spec.occupation_code)
    raw: dict[str, Any] = {
        "id": f"DM-F{spec.id.split('-F')[1]}",
        "employee": {"id": spec.employee_id, "name": spec.employee_name},
        "production": {
            "id": catalog.production["id"],
            "title": catalog.production["title"],
            "season": catalog.production["season"],
            "employer": catalog.production["employer"],
        },
        "occupation_code": spec.occupation_code,
        "occupation_title": scale.occupation,
        "guild": catalog.production["guild"],
        "hourly_rate_usd": str(scale.hourly_scale_usd),
        "scale_relationship": "at",
        "allowances": [],
        "department": spec.department,
        **{
            k: catalog.filler_location[k]
            for k in ("hire_state", "hire_city", "work_state", "primary_work_city")
        },
        "start_date": spec.start_date.isoformat(),
        "eligibility_verification": {
            "status": "completed",
            "completed_on": (spec.start_date + dt.timedelta(days=1)).isoformat(),
        },
        "conditions": [],
        "notes": f"Filler crew for scenario {spec.id} (clean week).",
    }
    return parse_deal_memo(raw)


def _filler_day(
    rng: random.Random, date: dt.date, weekday: str, catalog: Catalog, params: RuleParameters
) -> TimecardDay:
    """A clean day with seeded jitter: meal within the deadline, day well under the threshold."""
    j = catalog.filler_jitter
    call = rng.choice(j.call)
    meal_after = rng.choice(j.meal_after)
    after_meal = rng.choice(j.after_meal)
    meal_out = tenths(call + meal_after)
    meal_in = tenths(meal_out + catalog.late_meal_duration)
    wrap = tenths(meal_in + after_meal)
    if meal_after >= params.meal.deadline_hours:
        raise ValueError("filler_jitter.meal_after must stay under the meal deadline")
    if (wrap - call) - catalog.late_meal_duration >= params.extended_day.threshold_hours:
        raise ValueError("filler jitter produced a day at or above the extended day threshold")
    return TimecardDay(
        date=date,
        weekday=weekday,
        day_type=catalog.labels["day_type"]["work"],
        work_location=catalog.labels["work_location"]["stage"],
        call=call,
        meal_out=meal_out,
        meal_in=meal_in,
        wrap=wrap,
    )


def build_filler_timecard(
    spec: FillerSpec, memo: DealMemo, rng: random.Random, catalog: Catalog, params: RuleParameters
) -> Timecard:
    week_ending = catalog.demo_week_ending
    dates = _week_dates(week_ending)
    days = tuple(_filler_day(rng, dates[wd], wd, catalog, params) for wd in WEEKDAYS)
    return Timecard(
        id=_timecard_id(memo.employee_id, week_ending),
        scenario_id=spec.id,
        employee_id=memo.employee_id,
        employee_name=memo.employee_name,
        deal_memo_id=memo.id,
        occupation_code=memo.occupation_code,
        department=memo.department,
        week_ending=week_ending,
        producer_week=week_ending - dt.timedelta(days=6),
        status=catalog.queue_status,
        days=days,
    )


# ---------- generation ----------


def generate(
    catalog: Catalog | None = None,
    memos: dict[str, DealMemo] | None = None,
    params: RuleParameters | None = None,
    seed: int | None = None,
) -> GeneratedData:
    catalog = catalog or load_catalog()
    memos = memos or load_deal_memos()
    params = params or get_parameters()
    seed = catalog.seed if seed is None else seed
    rng = random.Random(seed)
    j = catalog.filler_jitter
    if max(j.meal_after) >= params.meal.deadline_hours:
        raise ValueError("filler_jitter.meal_after must stay under the meal deadline")
    if max(j.meal_after) + max(j.after_meal) >= params.extended_day.threshold_hours:
        raise ValueError("filler_jitter can produce a day at or above the extended day threshold")

    timecards: list[Timecard] = []
    for scenario in catalog.scenarios:
        memo = memos.get(scenario.deal_memo)
        if memo is None:
            raise ValueError(f"{scenario.id}: unknown deal memo {scenario.deal_memo}")
        timecards.append(build_scenario_timecard(scenario, memo, catalog, params))

    filler_memos: list[DealMemo] = []
    for spec in catalog.filler:
        memo = _filler_memo(spec, catalog, params)
        filler_memos.append(memo)
        timecards.append(build_filler_timecard(spec, memo, rng, catalog, params))

    keys = [(t.employee_id, t.week_ending) for t in timecards]
    if len(keys) != len(set(keys)):
        raise ValueError("an employee has two timecards for the same week ending")
    ids = [t.id for t in timecards]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate timecard ids")

    return GeneratedData(
        seed=seed,
        as_of_date=catalog.as_of_date,
        timecards=tuple(timecards),
        filler_deal_memos=tuple(filler_memos),
    )


# ---------- serialization ----------


def _plain(value: Any) -> Any:
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


def timecards_document(data: GeneratedData) -> dict[str, Any]:
    return _plain(
        {
            "generator": "payroll_triage.data.generator",
            "seed": data.seed,
            "as_of_date": data.as_of_date,
            "count": len(data.timecards),
            "timecards": [t.to_dict() for t in data.timecards],
        }
    )


def filler_memos_document(data: GeneratedData) -> dict[str, Any]:
    return {
        "generator": "payroll_triage.data.generator",
        "seed": data.seed,
        "deal_memos": [m.to_dict() for m in data.filler_deal_memos],
    }


def _dump(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, sort_keys=False, ensure_ascii=True) + "\n"


def write_generated(data: GeneratedData | None = None) -> list[Path]:
    data = data or generate()
    out_dir = generated_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, doc in (
        (TIMECARDS_FILE, timecards_document(data)),
        (FILLER_MEMOS_FILE, filler_memos_document(data)),
    ):
        path = out_dir / name
        path.write_text(_dump(doc), encoding="utf-8", newline="\n")
        written.append(path)
    return written


def check_generated(data: GeneratedData | None = None) -> list[str]:
    data = data or generate()
    problems: list[str] = []
    for name, doc in (
        (TIMECARDS_FILE, timecards_document(data)),
        (FILLER_MEMOS_FILE, filler_memos_document(data)),
    ):
        path = generated_dir() / name
        if not path.is_file():
            problems.append(f"generated file missing: {path}")
            continue
        committed = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        if committed != _dump(doc):
            problems.append(f"generated file is stale: {path}")
    return problems


def load_generated_timecards(path: Path | None = None) -> list[Timecard]:
    path = path or generated_dir() / TIMECARDS_FILE
    with path.open("r", encoding="utf-8") as fh:
        return [Timecard.from_dict(t) for t in json.load(fh)["timecards"]]
