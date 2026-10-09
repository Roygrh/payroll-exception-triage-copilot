"""End-to-end showcase on one scenario with the real adapter (`uv run ptc showcase`).

Runs detect, retrieve, explain, propose, draft, validate, pauses at the human
checkpoint, resumes with a decision, executes and audits. Prints every LLM
output verbatim plus the audit trail. Never prints configuration secrets.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from payroll_triage.data.generator import load_generated_timecards
from payroll_triage.graph.service import TriageService


def _p(title: str, value: Any) -> None:
    print(f"\n=== {title} ===")
    if isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, indent=2, ensure_ascii=True, default=str))


def run_showcase(
    service: TriageService,
    scenario_id: str,
    actor: str,
    decision_action: str,
    message: str | None,
) -> dict[str, Any]:
    """`decision_action` is the human's explicit choice. For a return, `message` is sent when
    given; otherwise the validated draft is sent verbatim; without either the run stops."""
    tc = next((t for t in load_generated_timecards() if t.scenario_id == scenario_id), None)
    if tc is None:
        raise ValueError(f"unknown scenario {scenario_id}")
    started = dt.datetime.now(dt.UTC)
    result = service.run_timecard(tc.id)
    _p("run (to the human checkpoint)", result)
    if result.get("case_id") is None:
        return {"scenario": scenario_id, "clean": True}
    case_id = result["case_id"]
    detail = service.case_detail(case_id)
    _p(
        "case",
        {
            k: detail["case"][k]
            for k in ("id", "policy_action", "amount_usd", "priority_score", "status")
        },
    )
    _p("findings", detail["case"]["findings"])
    _p("passages retrieved", detail["chunks"])
    status = detail["output_status"]
    _p(f"explanation (LLM, {status['explain']})", detail["explanation"])
    _p(f"proposal (LLM, {status['propose']})", detail["proposal"])
    _p(f"draft (LLM, {status['draft']})", detail["draft"])
    _p("validation (code)", detail["validation"])
    if detail.get("review_reason"):
        _p("needs human review", detail["review_reason"])
    _p("checkpoint", {"checkpoint_id": detail["checkpoint_id"], "waiting_on": detail["waiting_on"]})

    action = decision_action
    if action == "return" and not message:
        if status["draft"] == "valid":
            message = detail["draft"]["body"]  # the human accepts the validated draft as is
        else:
            raise ValueError(
                "a return needs --message: the case has no validated draft to send "
                f"(draft status {status['draft']})"
            )
    decision = {"action": action, "actor": actor, "message": message}
    outcome = service.decide(case_id, decision)
    _p("decision and execution", outcome)
    _p("audit trail", service.store.list_audit(case_id))
    calls = result.get("llm_calls", [])
    rate = next((c.get("rate_limit") for c in reversed(calls) if c.get("rate_limit")), {})
    summary = {
        "scenario": scenario_id,
        "case_id": case_id,
        "status_after": outcome["status"],
        "llm_calls": len(calls),
        "llm_call_summaries": calls,
        "rate_limit_headers_last_call": rate,
        "elapsed_seconds": (dt.datetime.now(dt.UTC) - started).total_seconds(),
    }
    _p("summary", summary)
    return summary
