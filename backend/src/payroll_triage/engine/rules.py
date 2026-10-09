"""Detection rules over a timecard (Iteration 2: MEAL_PERIOD).

The engine is tested against the committed eval manifest, which the oracle in
`evals/expectations.py` produced by construction. Both use `calc.py` for the
arithmetic and `policy.py` for the action, so they can only disagree on which
days are evaluated, which is exactly what the manifest test checks.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from payroll_triage import calc, policy
from payroll_triage.corpus.deal_memos import DealMemo
from payroll_triage.engine.facts import FACTS_SCHEMA_VERSION, MealPeriodFacts
from payroll_triage.engine.priority import PriorityInputs, priority_score
from payroll_triage.params import RuleParameters
from payroll_triage.timecards import DEFAULT_WORK_DAY_TYPE, Timecard


@dataclass(frozen=True)
class Finding:
    rule_id: str
    section: str
    citation_keys: tuple[str, ...]
    situation: str
    policy_action: str
    day_date: dt.date | None
    amount_usd: Decimal
    facts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "section": self.section,
            "citation_keys": list(self.citation_keys),
            "situation": self.situation,
            "policy_action": self.policy_action,
            "day_date": self.day_date.isoformat() if self.day_date else None,
            "amount_usd": f"{self.amount_usd:.2f}",
            "facts": self.facts,
            "facts_schema_version": FACTS_SCHEMA_VERSION,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Finding:
        return cls(
            rule_id=raw["rule_id"],
            section=raw["section"],
            citation_keys=tuple(raw["citation_keys"]),
            situation=raw["situation"],
            policy_action=raw["policy_action"],
            day_date=dt.date.fromisoformat(raw["day_date"]) if raw.get("day_date") else None,
            amount_usd=Decimal(raw["amount_usd"]),
            facts=dict(raw["facts"]),
        )


@dataclass(frozen=True)
class Detection:
    timecard_id: str
    findings: tuple[Finding, ...]
    policy_action: str
    amount_usd: Decimal
    priority_score: int

    @property
    def has_findings(self) -> bool:
        return bool(self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timecard_id": self.timecard_id,
            "findings": [f.to_dict() for f in self.findings],
            "policy_action": self.policy_action,
            "amount_usd": f"{self.amount_usd:.2f}",
            "priority_score": self.priority_score,
        }


def _citation_keys(params: RuleParameters, rule_id: str) -> tuple[str, ...]:
    ref = params.rule(rule_id)
    return (params.citation_key(ref.section),) + tuple(
        params.citation_key(s) for s in ref.related_sections
    )


def meal_period_rule(
    tc: Timecard, memo: DealMemo, params: RuleParameters, work_day_type: str
) -> list[Finding]:
    rule_id = "MEAL_PERIOD"
    out: list[Finding] = []
    for day in tc.work_days(work_day_type):
        if not day.is_chronological():
            continue  # incomplete days belong to TIME_ENTRY_COMPLETENESS (agreement 7.4)
        if day.is_no_meal_day(params):
            continue  # dismissed before the meal deadline (agreement 7.4 and 8.7)
        mf = calc.meal_facts(day.call, day.meal_out, day.meal_in, params)  # type: ignore[arg-type]
        if not (mf.is_late or mf.is_short):
            continue
        situation = policy.meal_situation(mf, policy.day_is_plausible(day, params))
        facts = MealPeriodFacts(
            hours_to_meal=mf.hours_to_meal,
            meal_minutes=mf.meal_minutes,
            minutes_late=mf.minutes_late,
            increments=mf.increments,
            penalty_usd=mf.penalty_usd,
            is_late=mf.is_late,
            is_short=mf.is_short,
            deadline_hours=params.meal.deadline_hours,
            min_duration_minutes=params.meal.min_duration_minutes,
            increment_minutes=params.meal.penalty_increment_minutes,
        )
        out.append(
            Finding(
                rule_id=rule_id,
                section=params.rule(rule_id).section,
                citation_keys=_citation_keys(params, rule_id),
                situation=str(situation),
                policy_action=policy.policy_action(situation),
                day_date=day.date,
                amount_usd=mf.penalty_usd,
                facts=facts.model_dump(mode="json"),
            )
        )
    return out


Rule = Callable[[Timecard, DealMemo, RuleParameters, str], list[Finding]]

_RULES: dict[str, Rule] = {"MEAL_PERIOD": meal_period_rule}


def wired_rules() -> tuple[str, ...]:
    return tuple(_RULES)


def detect(
    tc: Timecard,
    memo: DealMemo,
    params: RuleParameters,
    as_of: dt.date,
    payroll_run_date: dt.date,
    holidays: Iterable[dt.date] = (),
    work_day_type: str = DEFAULT_WORK_DAY_TYPE,
) -> Detection:
    findings: list[Finding] = []
    for rule in _RULES.values():
        findings.extend(rule(tc, memo, params, work_day_type))
    action = policy.combined_action(f.policy_action for f in findings)
    amount = calc.money(sum((f.amount_usd for f in findings), Decimal("0.00")))
    score = 0
    if findings:
        score = priority_score(
            PriorityInputs(
                policy_action=action,
                amount_usd=amount,
                week_ending=tc.week_ending,
                as_of=as_of,
                payroll_run_date=payroll_run_date,
                holidays=tuple(holidays),
            ),
            params,
        )
    return Detection(
        timecard_id=tc.id,
        findings=tuple(findings),
        policy_action=action,
        amount_usd=amount,
        priority_score=score,
    )
