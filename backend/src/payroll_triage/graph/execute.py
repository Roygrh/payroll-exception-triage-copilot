"""Execution plan: what code does with the human's decision (ADR-009, human identity).

Pure function; the store applies the plan in one transaction. Timecard status
labels follow the domain model, section 6.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from payroll_triage.db.store import ExecutionPlan, PremiumLine
from payroll_triage.policy import APPROVE, ESCALATE, RETURN

# Domain model, section 6; the runtime reads the same labels from the scenario catalog
# (`labels.timecard_status_after`) and a test checks they agree with these defaults.
TIMECARD_STATUS_AFTER: dict[str, str | None] = {
    APPROVE: "Ready for approver 2",
    RETURN: "Rejected",
    ESCALATE: None,
}
DEFAULT_INTAKE_STATUS = "Ready for approver 1"
CASE_STATUS_AFTER = {APPROVE: "approved", RETURN: "returned", ESCALATE: "escalated"}
DEFAULT_ESCALATION_NOTE = "Escalated by the approver to a payroll specialist; timecard unchanged."


class DecisionError(ValueError):
    pass


def validate_decision(decision: dict[str, Any]) -> dict[str, Any]:
    action = decision.get("action")
    if action not in TIMECARD_STATUS_AFTER:
        raise DecisionError(f"decision action must be approve, return or escalate, got {action!r}")
    actor = (decision.get("actor") or "").strip()
    if not actor:
        raise DecisionError("decision needs an actor (the human's identity)")
    message = decision.get("message")
    if action == RETURN and not (message or "").strip():
        raise DecisionError("a return decision needs the message to send")
    return {
        "action": action,
        "actor": actor,
        "message": (message or "").strip() or None,
        "recipient_role": decision.get("recipient_role") or "employee",
    }


def premium_lines_for(findings: list[dict[str, Any]]) -> tuple[PremiumLine, ...]:
    """Pay lines come from the engine's facts, never from generated text (ADR-008)."""
    lines = []
    for f in findings:
        amount = Decimal(f["amount_usd"])
        if amount <= 0:
            continue
        day = dt.date.fromisoformat(f["day_date"]) if f.get("day_date") else None
        lines.append(
            PremiumLine(
                rule_id=f["rule_id"],
                day_date=day,
                description=f"{f['rule_id']} premium per agreement section {f['section']}",
                amount_usd=amount,
            )
        )
    return tuple(lines)


def plan_execution(
    case_id: str,
    timecard_id: str,
    findings: list[dict[str, Any]],
    decision: dict[str, Any],
    status_after: dict[str, str | None] | None = None,
) -> ExecutionPlan:
    d = validate_decision(decision)
    action = d["action"]
    labels = status_after or TIMECARD_STATUS_AFTER
    plan = ExecutionPlan(
        case_id=case_id,
        timecard_id=timecard_id,
        action=action,
        actor=d["actor"],
        timecard_status_after=labels.get(action),
        case_status_after=CASE_STATUS_AFTER[action],
        decision_message=d["message"],
    )
    if action == APPROVE:
        return ExecutionPlan(**{**plan.__dict__, "premium_lines": premium_lines_for(findings)})
    if action == RETURN:
        return ExecutionPlan(
            **{
                **plan.__dict__,
                "return_message": d["message"],
                "recipient_role": d["recipient_role"],
            }
        )
    return ExecutionPlan(
        **{
            **plan.__dict__,
            "escalation_note": d["message"] or DEFAULT_ESCALATION_NOTE,
            "escalation_note_source": "human" if d["message"] else "default",
        }
    )
