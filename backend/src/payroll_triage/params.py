"""Loader for data/rule-parameters.yaml, the single source of truth (ADR-007).

The YAML is validated against data/rule-parameters.schema.json and then parsed
into frozen dataclasses so the rest of the code gets typed, immutable values.
Money is carried as Decimal to avoid float drift in amounts.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from payroll_triage.paths import rule_parameters_path, rule_parameters_schema_path


class ParameterError(ValueError):
    """Raised when the parameters file is missing, invalid or inconsistent."""


@dataclass(frozen=True)
class AgreementInfo:
    code: str
    name: str
    version: str
    effective_from: dt.date
    effective_to: dt.date
    guild: str
    employers: str
    citation_prefix: str

    def citation_key(self, section: str) -> str:
        return f"{self.citation_prefix}-{section}"

    def in_force_on(self, day: dt.date) -> bool:
        return self.effective_from <= day <= self.effective_to


@dataclass(frozen=True)
class PayrollInfo:
    week_start_day: str
    week_ending_day: str
    time_unit_hours: float
    currency: str


@dataclass(frozen=True)
class MealParams:
    deadline_hours: float
    min_duration_minutes: int
    penalty_increment_minutes: int
    penalty_schedule_usd: tuple[Decimal, ...]


@dataclass(frozen=True)
class ExtendedDayParams:
    threshold_hours: float
    multiplier: float


@dataclass(frozen=True)
class RestParams:
    min_hours: float
    invasion_multiplier: float


@dataclass(frozen=True)
class EligibilityParams:
    deadline_business_days: int


@dataclass(frozen=True)
class OvertimeParams:
    daily_after_hours: float
    daily_multiplier: float
    weekly_after_hours: float
    weekly_multiplier: float


@dataclass(frozen=True)
class PlausibilityParams:
    max_day_hours: float


@dataclass(frozen=True)
class QueueParams:
    urgency_business_days: int
    urgency_weight: int
    severity_weight: int
    amount_tier_thresholds_usd: tuple[Decimal, ...]
    max_days_late_points: int


@dataclass(frozen=True)
class ScaleEntry:
    code: str
    occupation: str
    hourly_scale_usd: Decimal


@dataclass(frozen=True)
class RuleRef:
    rule_id: str
    section: str
    title: str
    related_sections: tuple[str, ...]


@dataclass(frozen=True)
class RuleParameters:
    agreement: AgreementInfo
    payroll: PayrollInfo
    meal: MealParams
    extended_day: ExtendedDayParams
    rest: RestParams
    eligibility: EligibilityParams
    overtime: OvertimeParams
    plausibility: PlausibilityParams
    queue: QueueParams
    schedule_a: tuple[ScaleEntry, ...]
    rules: dict[str, RuleRef]
    raw: dict[str, Any]

    def scale_for(self, code: str) -> ScaleEntry:
        for entry in self.schedule_a:
            if entry.code == code:
                return entry
        raise ParameterError(f"occupation code {code!r} is not in Schedule A")

    def rule(self, rule_id: str) -> RuleRef:
        try:
            return self.rules[rule_id]
        except KeyError as exc:
            raise ParameterError(f"unknown rule id {rule_id!r}") from exc

    def citation_key(self, section: str) -> str:
        return self.agreement.citation_key(section)


def _money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _date(value: Any) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def _jsonable(value: Any) -> Any:
    """YAML parses ISO dates into date objects; the schema expects strings."""
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def validate_raw(raw: dict[str, Any], schema: dict[str, Any]) -> None:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(_jsonable(raw)), key=lambda e: list(e.absolute_path))
    if errors:
        lines = [
            f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors
        ]
        raise ParameterError("rule parameters failed schema validation:\n  " + "\n  ".join(lines))


def _semantic_checks(p: RuleParameters) -> None:
    problems: list[str] = []
    if p.agreement.effective_from > p.agreement.effective_to:
        problems.append("agreement.effective_from is after effective_to")
    expected_prefix = f"{p.agreement.code}-{p.agreement.version}"
    if p.agreement.citation_prefix != expected_prefix:
        problems.append(f"agreement.citation_prefix must be {expected_prefix!r}")
    if p.extended_day.threshold_hours <= p.overtime.daily_after_hours:
        problems.append("extended_day.threshold_hours must exceed overtime.daily_after_hours")
    if p.meal.deadline_hours >= p.extended_day.threshold_hours:
        problems.append("meal.deadline_hours must be below extended_day.threshold_hours")
    tiers = list(p.queue.amount_tier_thresholds_usd)
    if tiers != sorted(tiers) or len(tiers) != len(set(tiers)):
        problems.append("queue.amount_tier_thresholds_usd must be strictly increasing")
    codes = [e.code for e in p.schedule_a]
    if len(codes) != len(set(codes)):
        problems.append("schedule_a has duplicate occupation codes")
    # Hour-valued parameters must be representable in the timecard recording unit,
    # otherwise the agreement text and the engine could disagree on a rounded value.
    unit = Decimal(str(p.payroll.time_unit_hours))
    for name, value in (
        ("meal.deadline_hours", p.meal.deadline_hours),
        ("extended_day.threshold_hours", p.extended_day.threshold_hours),
        ("rest.min_hours", p.rest.min_hours),
        ("overtime.daily_after_hours", p.overtime.daily_after_hours),
        ("overtime.weekly_after_hours", p.overtime.weekly_after_hours),
        ("plausibility.max_day_hours", p.plausibility.max_day_hours),
    ):
        if (Decimal(str(value)) % unit) != 0:
            problems.append(f"{name} must be a multiple of payroll.time_unit_hours ({unit})")
    if problems:
        raise ParameterError("rule parameters failed semantic checks:\n  " + "\n  ".join(problems))


def parse_parameters(raw: dict[str, Any], schema: dict[str, Any]) -> RuleParameters:
    validate_raw(raw, schema)
    a = raw["agreement"]
    rules = {
        rule_id: RuleRef(
            rule_id=rule_id,
            section=str(spec["section"]),
            title=spec["title"],
            related_sections=tuple(str(s) for s in spec["related_sections"]),
        )
        for rule_id, spec in raw["rules"].items()
    }
    params = RuleParameters(
        agreement=AgreementInfo(
            code=a["code"],
            name=a["name"],
            version=str(a["version"]),
            effective_from=_date(a["effective_from"]),
            effective_to=_date(a["effective_to"]),
            guild=a["parties"]["guild"],
            employers=a["parties"]["employers"],
            citation_prefix=a["citation_prefix"],
        ),
        payroll=PayrollInfo(**raw["payroll"]),
        meal=MealParams(
            deadline_hours=float(raw["meal"]["deadline_hours"]),
            min_duration_minutes=int(raw["meal"]["min_duration_minutes"]),
            penalty_increment_minutes=int(raw["meal"]["penalty_increment_minutes"]),
            penalty_schedule_usd=tuple(_money(v) for v in raw["meal"]["penalty_schedule_usd"]),
        ),
        extended_day=ExtendedDayParams(
            threshold_hours=float(raw["extended_day"]["threshold_hours"]),
            multiplier=float(raw["extended_day"]["multiplier"]),
        ),
        rest=RestParams(
            min_hours=float(raw["rest"]["min_hours"]),
            invasion_multiplier=float(raw["rest"]["invasion_multiplier"]),
        ),
        eligibility=EligibilityParams(
            deadline_business_days=int(raw["eligibility"]["deadline_business_days"])
        ),
        overtime=OvertimeParams(**{k: float(v) for k, v in raw["overtime"].items()}),
        plausibility=PlausibilityParams(max_day_hours=float(raw["plausibility"]["max_day_hours"])),
        queue=QueueParams(
            urgency_business_days=int(raw["queue"]["urgency_business_days"]),
            urgency_weight=int(raw["queue"]["urgency_weight"]),
            severity_weight=int(raw["queue"]["severity_weight"]),
            amount_tier_thresholds_usd=tuple(
                _money(v) for v in raw["queue"]["amount_tier_thresholds_usd"]
            ),
            max_days_late_points=int(raw["queue"]["max_days_late_points"]),
        ),
        schedule_a=tuple(
            ScaleEntry(
                code=str(e["code"]),
                occupation=e["occupation"],
                hourly_scale_usd=_money(e["hourly_scale_usd"]),
            )
            for e in raw["schedule_a"]
        ),
        rules=rules,
        raw=raw,
    )
    _semantic_checks(params)
    return params


def load_raw(path: Path | None = None) -> dict[str, Any]:
    path = path or rule_parameters_path()
    if not path.is_file():
        raise ParameterError(f"rule parameters file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ParameterError("rule parameters file must contain a mapping at the top level")
    return raw


def load_schema(path: Path | None = None) -> dict[str, Any]:
    path = path or rule_parameters_schema_path()
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_parameters(path: Path | None = None, schema_path: Path | None = None) -> RuleParameters:
    return parse_parameters(load_raw(path), load_schema(schema_path))


@lru_cache(maxsize=1)
def get_parameters() -> RuleParameters:
    """Cached default parameters for application code."""
    return load_parameters()
