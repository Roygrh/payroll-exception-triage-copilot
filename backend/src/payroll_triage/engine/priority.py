"""Queue priority (domain model, section 3; parameters in the `queue` block of the YAML).

score = urgency_weight x urgency + severity_weight x severity rank + amount tier
        + min(business days late, max_days_late_points)

urgency is 1 when the payroll run is within `urgency_business_days` of the queue
date, else 0. Higher scores are worked first; ties break by week ending, oldest
first (the ordering is applied by the queue query, not here).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from payroll_triage import calc, policy
from payroll_triage.params import RuleParameters


@dataclass(frozen=True)
class PriorityInputs:
    policy_action: str
    amount_usd: Decimal
    week_ending: dt.date
    as_of: dt.date
    payroll_run_date: dt.date
    holidays: tuple[dt.date, ...] = ()


def amount_tier(amount_usd: Decimal, params: RuleParameters) -> int:
    tier = 0
    for threshold in params.queue.amount_tier_thresholds_usd:
        if amount_usd >= threshold:
            tier += 1
    return tier


def is_urgent(
    as_of: dt.date, payroll_run_date: dt.date, params: RuleParameters, holidays=()
) -> bool:
    days = calc.business_days_between(as_of, payroll_run_date, holidays)
    return payroll_run_date >= as_of and days <= params.queue.urgency_business_days


def days_late(week_ending: dt.date, as_of: dt.date, holidays=()) -> int:
    return calc.business_days_between(week_ending, as_of, holidays)


def priority_score(inputs: PriorityInputs, params: RuleParameters) -> int:
    q = params.queue
    urgency = 1 if is_urgent(inputs.as_of, inputs.payroll_run_date, params, inputs.holidays) else 0
    severity = policy.SEVERITY[inputs.policy_action]
    late = min(days_late(inputs.week_ending, inputs.as_of, inputs.holidays), q.max_days_late_points)
    return (
        q.urgency_weight * urgency
        + q.severity_weight * severity
        + amount_tier(inputs.amount_usd, params)
        + late
    )
