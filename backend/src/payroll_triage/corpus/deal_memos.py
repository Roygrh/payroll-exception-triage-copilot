"""Deal memo loading and scale checks (P1.I1.S4)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml

from payroll_triage.params import RuleParameters, get_parameters
from payroll_triage.paths import deal_memos_dir

ScaleRelationship = Literal["above", "at", "below"]
EligibilityStatus = Literal["pending", "completed"]


class DealMemoError(ValueError):
    pass


@dataclass(frozen=True)
class Allowance:
    type: str
    amount_usd: Decimal
    period: str
    description: str = ""


@dataclass(frozen=True)
class DealMemo:
    id: str
    employee_id: str
    employee_name: str
    production_id: str
    production_title: str
    season: int
    employer: str
    occupation_code: str
    occupation_title: str
    guild: str
    hourly_rate_usd: Decimal
    scale_relationship: ScaleRelationship
    department: str
    hire_state: str
    hire_city: str
    work_state: str
    primary_work_city: str
    start_date: dt.date
    eligibility_status: EligibilityStatus
    eligibility_completed_on: dt.date | None
    allowances: tuple[Allowance, ...] = ()
    conditions: tuple[str, ...] = ()
    notes: str = ""
    source_path: Path | None = field(default=None, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "employee": {"id": self.employee_id, "name": self.employee_name},
            "production": {
                "id": self.production_id,
                "title": self.production_title,
                "season": self.season,
                "employer": self.employer,
            },
            "occupation_code": self.occupation_code,
            "occupation_title": self.occupation_title,
            "guild": self.guild,
            "hourly_rate_usd": f"{self.hourly_rate_usd:.2f}",
            "scale_relationship": self.scale_relationship,
            "allowances": [
                {
                    "type": a.type,
                    "amount_usd": f"{a.amount_usd:.2f}",
                    "period": a.period,
                    "description": a.description,
                }
                for a in self.allowances
            ],
            "department": self.department,
            "hire_state": self.hire_state,
            "hire_city": self.hire_city,
            "work_state": self.work_state,
            "primary_work_city": self.primary_work_city,
            "start_date": self.start_date.isoformat(),
            "eligibility_verification": {
                "status": self.eligibility_status,
                "completed_on": (
                    self.eligibility_completed_on.isoformat()
                    if self.eligibility_completed_on
                    else None
                ),
            },
            "conditions": list(self.conditions),
            "notes": self.notes,
        }


def _money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _date(value: Any) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


REQUIRED_KEYS = (
    "id",
    "employee",
    "production",
    "occupation_code",
    "occupation_title",
    "guild",
    "hourly_rate_usd",
    "scale_relationship",
    "allowances",
    "department",
    "hire_state",
    "hire_city",
    "work_state",
    "primary_work_city",
    "start_date",
    "eligibility_verification",
)


def parse_deal_memo(raw: dict[str, Any], source: Path | None = None) -> DealMemo:
    missing = [k for k in REQUIRED_KEYS if k not in raw]
    if missing:
        raise DealMemoError(f"{source or raw.get('id')}: missing keys {missing}")
    if raw["scale_relationship"] not in ("above", "at", "below"):
        raise DealMemoError(f"{raw['id']}: invalid scale_relationship")
    ev = raw["eligibility_verification"]
    if ev.get("status") not in ("pending", "completed"):
        raise DealMemoError(f"{raw['id']}: invalid eligibility status")
    completed_on = _date(ev.get("completed_on"))
    if ev["status"] == "completed" and completed_on is None:
        raise DealMemoError(f"{raw['id']}: completed verification needs completed_on")
    if ev["status"] == "pending" and completed_on is not None:
        raise DealMemoError(f"{raw['id']}: pending verification must not have completed_on")
    return DealMemo(
        id=raw["id"],
        employee_id=raw["employee"]["id"],
        employee_name=raw["employee"]["name"],
        production_id=raw["production"]["id"],
        production_title=raw["production"]["title"],
        season=int(raw["production"]["season"]),
        employer=raw["production"]["employer"],
        occupation_code=str(raw["occupation_code"]),
        occupation_title=raw["occupation_title"],
        guild=raw["guild"],
        hourly_rate_usd=_money(raw["hourly_rate_usd"]),
        scale_relationship=raw["scale_relationship"],
        department=raw["department"],
        hire_state=raw["hire_state"],
        hire_city=raw["hire_city"],
        work_state=raw["work_state"],
        primary_work_city=raw["primary_work_city"],
        start_date=_date(raw["start_date"]),  # type: ignore[arg-type]
        eligibility_status=ev["status"],
        eligibility_completed_on=completed_on,
        allowances=tuple(
            Allowance(
                type=a["type"],
                amount_usd=_money(a["amount_usd"]),
                period=a["period"],
                description=a.get("description", ""),
            )
            for a in raw.get("allowances", [])
        ),
        conditions=tuple(raw.get("conditions", [])),
        notes=raw.get("notes", ""),
        source_path=source,
    )


def load_deal_memo(path: Path) -> DealMemo:
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise DealMemoError(f"{path}: expected a mapping")
    return parse_deal_memo(raw, path)


def load_deal_memos(directory: Path | None = None) -> dict[str, DealMemo]:
    directory = directory or deal_memos_dir()
    memos: dict[str, DealMemo] = {}
    for path in sorted(directory.glob("DM-*.yaml")):
        memo = load_deal_memo(path)
        if memo.id in memos:
            raise DealMemoError(f"duplicate deal memo id {memo.id}")
        memos[memo.id] = memo
    if not memos:
        raise DealMemoError(f"no deal memos found in {directory}")
    return memos


def actual_scale_relationship(memo: DealMemo, params: RuleParameters) -> ScaleRelationship:
    scale = params.scale_for(memo.occupation_code).hourly_scale_usd
    if memo.hourly_rate_usd < scale:
        return "below"
    if memo.hourly_rate_usd == scale:
        return "at"
    return "above"


def scale_shortfall(memo: DealMemo, params: RuleParameters) -> Decimal:
    """Positive when the memo rate is below scale, else zero."""
    scale = params.scale_for(memo.occupation_code).hourly_scale_usd
    return max(Decimal("0.00"), scale - memo.hourly_rate_usd)


def check_deal_memos(
    memos: dict[str, DealMemo] | None = None, params: RuleParameters | None = None
) -> list[str]:
    """Consistency problems between the memos and Schedule A; empty when consistent."""
    params = params or get_parameters()
    memos = memos or load_deal_memos()
    problems: list[str] = []
    for memo in memos.values():
        try:
            entry = params.scale_for(memo.occupation_code)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{memo.id}: {exc}")
            continue
        if memo.occupation_title != entry.occupation:
            problems.append(
                f"{memo.id}: occupation title {memo.occupation_title!r} does not match "
                f"Schedule A {entry.occupation!r} for code {memo.occupation_code}"
            )
        actual = actual_scale_relationship(memo, params)
        if actual != memo.scale_relationship:
            problems.append(
                f"{memo.id}: declares {memo.scale_relationship} scale but rate "
                f"{memo.hourly_rate_usd} versus scale {entry.hourly_scale_usd} is {actual}"
            )
    return problems
