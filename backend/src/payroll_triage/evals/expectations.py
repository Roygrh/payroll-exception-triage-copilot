"""Expected findings derived by construction from generated timecards.

This is the ground-truth oracle for the evaluation manifest (ADR-003 tier 1)
and for the generator tests. It uses the same arithmetic helpers the rule
engine will use (ADR-007, ADR-008). The engine built in Iteration 2 must
reproduce these findings; it is tested against the manifest, not the reverse.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from payroll_triage import calc, policy
from payroll_triage.corpus.deal_memos import DealMemo, scale_shortfall
from payroll_triage.params import RuleParameters
from payroll_triage.timecards import DEFAULT_WORK_DAY_TYPE, TIME_FIELDS, Timecard, TimecardDay

APPROVE, RETURN, ESCALATE = policy.APPROVE, policy.RETURN, policy.ESCALATE


@dataclass(frozen=True)
class ExpectedFinding:
    rule_id: str
    section: str
    citation_keys: tuple[str, ...]
    policy_action: str
    day_date: dt.date | None
    facts: dict[str, Any] = field(default_factory=dict)


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, dt.date):
        return value.isoformat()
    return value


def _facts(obj: Any, **extra: Any) -> dict[str, Any]:
    data = dict(obj.__dict__) if hasattr(obj, "__dict__") else {}
    data.update(extra)
    return {k: _plain(v) for k, v in data.items()}


def _keys(params: RuleParameters, rule_id: str) -> tuple[str, ...]:
    ref = params.rule(rule_id)
    return (params.citation_key(ref.section),) + tuple(
        params.citation_key(s) for s in ref.related_sections
    )


_day_plausible = policy.day_is_plausible


def work_days(tc: Timecard, work_day_type: str = DEFAULT_WORK_DAY_TYPE) -> list[TimecardDay]:
    """Only work days are evaluated by the rules (domain model, section 6)."""
    return tc.work_days(work_day_type)


def completeness_findings(
    tc: Timecard, params: RuleParameters, work_day_type: str = DEFAULT_WORK_DAY_TYPE
) -> list[ExpectedFinding]:
    out = []
    rule = "TIME_ENTRY_COMPLETENESS"
    for day in work_days(tc, work_day_type):
        missing = [f for f in TIME_FIELDS if getattr(day, f) is None]
        out_of_order = day.is_complete() and not day.is_chronological()
        if missing or out_of_order:
            out.append(
                ExpectedFinding(
                    rule_id=rule,
                    section=params.rule(rule).section,
                    citation_keys=_keys(params, rule),
                    policy_action=policy.policy_action(policy.completeness_situation()),
                    day_date=day.date,
                    facts={
                        "missing_entries": missing,
                        "entries_out_of_order": out_of_order,
                        "entries": {f: getattr(day, f) for f in TIME_FIELDS},
                    },
                )
            )
    return out


def meal_findings(
    tc: Timecard, params: RuleParameters, work_day_type: str = DEFAULT_WORK_DAY_TYPE
) -> list[ExpectedFinding]:
    out = []
    rule = "MEAL_PERIOD"
    for day in work_days(tc, work_day_type):
        if not day.is_chronological():
            continue
        if day.is_no_meal_day(params):
            # Dismissed before the meal deadline (agreement 7.4 and 8.7): no finding.
            continue
        mf = calc.meal_facts(day.call, day.meal_out, day.meal_in, params)  # type: ignore[arg-type]
        if not (mf.is_late or mf.is_short):
            continue
        action = policy.policy_action(policy.meal_situation(mf, _day_plausible(day, params)))
        out.append(
            ExpectedFinding(
                rule_id=rule,
                section=params.rule(rule).section,
                citation_keys=_keys(params, rule),
                policy_action=action,
                day_date=day.date,
                facts=_facts(
                    mf,
                    deadline_hours=params.meal.deadline_hours,
                    min_duration_minutes=params.meal.min_duration_minutes,
                    increment_minutes=params.meal.penalty_increment_minutes,
                ),
            )
        )
    return out


def extended_day_findings(
    tc: Timecard,
    memo: DealMemo,
    params: RuleParameters,
    work_day_type: str = DEFAULT_WORK_DAY_TYPE,
) -> list[ExpectedFinding]:
    out = []
    rule = "EXTENDED_DAY"
    for day in work_days(tc, work_day_type):
        if not day.is_chronological():
            continue
        hf = calc.day_hours_facts(day.call, day.meal_out, day.meal_in, day.wrap, params)  # type: ignore[arg-type]
        if hf.hours_over_threshold <= 0:
            continue
        premium = calc.premium_amount(
            hf.hours_over_threshold, memo.hourly_rate_usd, params.extended_day.multiplier
        )
        out.append(
            ExpectedFinding(
                rule_id=rule,
                section=params.rule(rule).section,
                citation_keys=_keys(params, rule),
                policy_action=policy.policy_action(
                    policy.premium_situation(_day_plausible(day, params))
                ),
                day_date=day.date,
                facts=_facts(
                    hf,
                    threshold_hours=params.extended_day.threshold_hours,
                    hourly_rate_usd=memo.hourly_rate_usd,
                    premium_usd=premium,
                ),
            )
        )
    return out


def rest_findings(
    tc: Timecard,
    memo: DealMemo,
    params: RuleParameters,
    work_day_type: str = DEFAULT_WORK_DAY_TYPE,
) -> list[ExpectedFinding]:
    out = []
    rule = "REST_PERIOD"
    days = work_days(tc, work_day_type)
    for prev, nxt in zip(days, days[1:], strict=False):
        if prev.wrap is None or nxt.call is None:
            continue
        if (nxt.date - prev.date).days != 1:
            continue
        rf = calc.rest_facts(prev.wrap, nxt.call, params)
        if not rf.is_invaded:
            continue
        invasion_pay = calc.premium_amount(
            rf.invaded_hours, memo.hourly_rate_usd, params.rest.invasion_multiplier
        )
        plausible = _day_plausible(prev, params) and _day_plausible(nxt, params)
        out.append(
            ExpectedFinding(
                rule_id=rule,
                section=params.rule(rule).section,
                citation_keys=_keys(params, rule),
                policy_action=policy.policy_action(policy.premium_situation(plausible)),
                day_date=nxt.date,
                facts=_facts(
                    rf,
                    previous_wrap=prev.wrap,
                    previous_date=prev.date,
                    next_call=nxt.call,
                    min_rest_hours=params.rest.min_hours,
                    hourly_rate_usd=memo.hourly_rate_usd,
                    invasion_pay_usd=invasion_pay,
                ),
            )
        )
    return out


def scale_findings(memo: DealMemo, params: RuleParameters) -> list[ExpectedFinding]:
    shortfall = scale_shortfall(memo, params)
    if shortfall <= 0:
        return []
    rule = "SCALE_RATE"
    scale = params.scale_for(memo.occupation_code)
    return [
        ExpectedFinding(
            rule_id=rule,
            section=params.rule(rule).section,
            citation_keys=_keys(params, rule),
            policy_action=policy.policy_action(policy.compliance_situation()),
            day_date=None,
            facts={
                "occupation_code": memo.occupation_code,
                "occupation": scale.occupation,
                "scale_usd": _plain(scale.hourly_scale_usd),
                "deal_memo_rate_usd": _plain(memo.hourly_rate_usd),
                "shortfall_per_hour_usd": _plain(shortfall),
                "deal_memo_id": memo.id,
            },
        )
    ]


def eligibility_findings(
    memo: DealMemo,
    as_of: dt.date,
    params: RuleParameters,
    holidays: Iterable[dt.date] = (),
) -> list[ExpectedFinding]:
    ef = calc.eligibility_facts(
        memo.start_date, memo.eligibility_completed_on, as_of, params, holidays
    )
    if not ef.is_overdue:
        return []
    rule = "ELIGIBILITY_DOC"
    return [
        ExpectedFinding(
            rule_id=rule,
            section=params.rule(rule).section,
            citation_keys=_keys(params, rule),
            policy_action=policy.policy_action(policy.compliance_situation()),
            day_date=None,
            facts=_facts(
                ef,
                deadline_business_days=params.eligibility.deadline_business_days,
                deal_memo_id=memo.id,
            ),
        )
    ]


def expected_findings(
    tc: Timecard,
    memo: DealMemo,
    params: RuleParameters,
    as_of: dt.date,
    holidays: Iterable[dt.date] = (),
    work_day_type: str = DEFAULT_WORK_DAY_TYPE,
) -> list[ExpectedFinding]:
    findings: list[ExpectedFinding] = []
    findings += completeness_findings(tc, params, work_day_type)
    findings += meal_findings(tc, params, work_day_type)
    findings += extended_day_findings(tc, memo, params, work_day_type)
    findings += rest_findings(tc, memo, params, work_day_type)
    findings += scale_findings(memo, params)
    findings += eligibility_findings(memo, as_of, params, holidays)
    return findings


def combined_action(findings: Iterable[ExpectedFinding]) -> str:
    """Most severe policy action wins (ADR-009); 'none' when there are no findings."""
    return policy.combined_action(f.policy_action for f in findings)
