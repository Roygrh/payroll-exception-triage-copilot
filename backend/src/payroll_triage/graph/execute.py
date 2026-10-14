"""Execution plan: what code does with the human's decision (ADR-009, human identity).

Pure functions; the store applies the plan in one transaction. Timecard status
labels follow the domain model, section 6. The human acts at two interrupts
(ADR-018): the choice of action, then, for return and escalate, the
confirmation of the message. No message is ever produced by code.
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
MESSAGE_ACTIONS = (RETURN, ESCALATE)
# Who a message may be addressed to, per action; the first is the code default when the human
# does not name a recipient. The draft's own recipient is only a suggestion (ADR-018).
RECIPIENTS: dict[str, tuple[str, ...]] = {
    RETURN: ("employee", "department_head"),
    ESCALATE: ("payroll_specialist",),
}
MAX_MESSAGE_LENGTH = 4000


class DecisionError(ValueError):
    pass


def _actor(raw: dict[str, Any]) -> str:
    actor = (raw.get("actor") or "").strip()
    if not actor:
        raise DecisionError("decision needs an actor (the human's identity)")
    return actor


def validate_choice(choice: dict[str, Any]) -> dict[str, Any]:
    """Interrupt 1: the action and the human who chose it. No message at this step."""
    action = choice.get("action")
    if action not in TIMECARD_STATUS_AFTER:
        raise DecisionError(f"decision action must be approve, return or escalate, got {action!r}")
    if choice.get("message") is not None:
        raise DecisionError(
            "the message is confirmed after the action is chosen (POST /cases/{id}/message)"
        )
    return {"action": action, "actor": _actor(choice)}


def validate_message(reply: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Interrupt 2: a confirmed message from the chooser, or a cancel from any actor."""
    actor = _actor(reply)
    if reply.get("cancel"):
        if reply.get("message") is not None:
            raise DecisionError("cancel and message are exclusive")
        return {"cancel": True, "actor": actor}
    if actor != decision["actor"]:
        raise DecisionError(
            f"the message must be confirmed by {decision['actor']!r}, who chose the action "
            "(any actor may cancel)"
        )
    message = (reply.get("message") or "").strip()
    if not message:
        raise DecisionError(f"a {decision['action']} needs the message to send")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise DecisionError(f"the message is longer than {MAX_MESSAGE_LENGTH} characters")
    allowed = RECIPIENTS[decision["action"]]
    recipient = reply.get("recipient_role") or allowed[0]
    if recipient not in allowed:
        raise DecisionError(f"a {decision['action']} goes to one of {list(allowed)}")
    return {"cancel": False, "actor": actor, "message": message, "recipient_role": recipient}


def message_source(confirmed: str, draft_body: str | None) -> str:
    if not draft_body:
        return "human_written"
    return "draft_confirmed" if confirmed == draft_body.strip() else "draft_edited"


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
    """`decision` is the validated choice plus, for return and escalate, the confirmed message
    (`message`, `recipient_role`, `message_source`)."""
    action = decision.get("action")
    if action not in TIMECARD_STATUS_AFTER:
        raise DecisionError(f"decision action must be approve, return or escalate, got {action!r}")
    actor = _actor(decision)
    message = (decision.get("message") or "").strip() or None
    if action in MESSAGE_ACTIONS and message is None:
        raise DecisionError(f"a {action} needs the confirmed message to send")
    if action == APPROVE and message is not None:
        raise DecisionError("an approve sends no message")
    labels = status_after or TIMECARD_STATUS_AFTER
    plan = ExecutionPlan(
        case_id=case_id,
        timecard_id=timecard_id,
        action=action,
        actor=actor,
        timecard_status_after=labels.get(action),
        case_status_after=CASE_STATUS_AFTER[action],
        decision_message=message,
        message_source=decision.get("message_source") if message else None,
    )
    if action == APPROVE:
        return ExecutionPlan(**{**plan.__dict__, "premium_lines": premium_lines_for(findings)})
    if action == RETURN:
        return ExecutionPlan(
            **{
                **plan.__dict__,
                "return_message": message,
                "recipient_role": decision.get("recipient_role") or RECIPIENTS[RETURN][0],
            }
        )
    return ExecutionPlan(**{**plan.__dict__, "escalation_note": message})
