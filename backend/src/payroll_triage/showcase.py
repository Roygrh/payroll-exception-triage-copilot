"""End-to-end showcase on one scenario (`uv run ptc showcase`), ADR-018 flow.

Runs detect, retrieve, explain_propose, validate and pauses at the human checkpoint; resumes
with the human's action. Approve executes. Return and escalate draft the message for that
action and stop at the message step, so the human reads the draft before confirming it with
`ptc confirm-message` (`--accept-draft`, `--message` or `--cancel`); `--message` on the showcase
sends text the human wrote in advance.
Prints every LLM output verbatim, the audit trail and the tokens per call and per case. Never
prints configuration secrets.

`--dry-run` builds the same prompts offline and prints estimated input tokens (ADR-019); it
needs no database, no key and makes no provider call.
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


def token_totals(calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Tokens per call and per case, as reported by the provider (`usage`)."""
    per_call = []
    total_in = total_out = 0
    for c in calls:
        tin, tout = c.get("input_tokens") or 0, c.get("output_tokens") or 0
        total_in += tin
        total_out += tout
        per_call.append(
            {
                "node": c.get("node"),
                "input_tokens": c.get("input_tokens"),
                "output_tokens": c.get("output_tokens"),
                "total_tokens": tin + tout,
                "attempts": c.get("attempts"),
                "error": c.get("error"),
            }
        )
    return {
        "llm_calls": len(calls),
        "per_call": per_call,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "total_tokens_per_case": total_in + total_out,
    }


def _scenario_timecard(scenario_id: str):
    tc = next((t for t in load_generated_timecards() if t.scenario_id == scenario_id), None)
    if tc is None:
        raise ValueError(f"unknown scenario {scenario_id}")
    return tc


def confirm(
    service: TriageService,
    case_id: str,
    actor: str,
    message: str | None,
    accept_draft: bool,
    cancel: bool = False,
) -> dict[str, Any] | None:
    """Resume the message step on an explicit human instruction only; None when there is none."""
    if cancel:
        return service.confirm_message(case_id, {"actor": actor, "cancel": True})
    if message:
        return service.confirm_message(case_id, {"actor": actor, "message": message})
    if accept_draft:
        detail = service.case_detail(case_id)
        if detail["output_status"]["draft"] != "valid" or not detail["draft"]:
            raise ValueError(
                "--accept-draft needs a validated draft (draft status "
                f"{detail['output_status']['draft']}); write the message with --message"
            )
        return service.confirm_message(
            case_id,
            {
                "actor": actor,
                "message": detail["draft"]["body"],
                "recipient_role": detail["draft"]["recipient_role"],
            },
        )
    return None


def run_showcase(
    service: TriageService,
    scenario_id: str,
    actor: str,
    decision_action: str,
    message: str | None = None,
) -> dict[str, Any]:
    """`decision_action` is the human's explicit choice; never defaulted by code. A drafted
    message is never accepted here: the human reads it first (`ptc confirm-message`)."""
    tc = _scenario_timecard(scenario_id)
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
    _p("passages retrieved (sent_to_model marks the passages in the prompt)", detail["chunks"])
    status = detail["output_status"]
    _p(f"explanation (LLM, {status['explain']})", detail["explanation"])
    _p(f"proposal (LLM, {status['propose']})", detail["proposal"])
    _p("validation (code)", detail["validation"])
    if detail.get("review_reason"):
        _p("needs human review", detail["review_reason"])
    _p("checkpoint", {"checkpoint_id": detail["checkpoint_id"], "waiting_on": detail["waiting_on"]})

    outcome = service.decide(case_id, {"action": decision_action, "actor": actor})
    if outcome["waiting_on"] == ["message_checkpoint"]:
        _p(
            f"draft for the {decision_action} (LLM, {outcome['draft_status']})",
            outcome["draft"] or "(no validated draft: the human writes the message)",
        )
        if outcome.get("review_reason"):
            _p("needs human review", outcome["review_reason"])
        confirmed = confirm(service, case_id, actor, message, False)
        if confirmed is None:
            _p(
                "stopped at the message step",
                f"confirm with: uv run ptc confirm-message --case {case_id} --actor {actor} "
                '(--accept-draft | --message "..." | --cancel)',
            )
        else:
            outcome = confirmed
    _p("decision and execution", {k: v for k, v in outcome.items() if k != "llm_calls"})
    _p("audit trail", service.store.list_audit(case_id))
    calls = service.case_detail(case_id)["llm_calls"]
    rate = next((c.get("rate_limit") for c in reversed(calls) if c.get("rate_limit")), {})
    tokens = token_totals(calls)
    summary = {
        "scenario": scenario_id,
        "case_id": case_id,
        "status_after": outcome["status"],
        "waiting_on": outcome["waiting_on"],
        "tokens": tokens,
        "rate_limit_headers_last_call": rate,
        "elapsed_seconds": (dt.datetime.now(dt.UTC) - started).total_seconds(),
    }
    _p("summary", summary)
    print(
        f"\nTOKENS PER CASE ({scenario_id}): {tokens['total_tokens_per_case']} "
        f"(input {tokens['input_tokens']}, output {tokens['output_tokens']}, "
        f"{tokens['llm_calls']} calls)"
    )
    return summary


# ---------- offline dry run (ADR-019) ----------

# The draft prompt includes the validated explanation and, for a return, the requested
# correction. Offline there is no model output, so these placeholders stand in for them; their
# size is about one short paragraph per finding (the outputs of the first real run).
PLACEHOLDER_EXPLANATION = (
    "On the work day the first meal began after the deadline set by the agreement for the "
    "first meal period after call [KEY]. The timecard shows the facts given by the rule "
    "engine for hours to meal and minutes late, which places the meal outside the allowed "
    "window and makes the penalty increments under the schedule payable [KEY]. The crew "
    "member's deal memo sets the terms that apply to this engagement [KEY]."
)
PLACEHOLDER_CORRECTION = (
    "Confirm or correct the recorded meal out and meal in entries for the day, and submit the "
    "corrected timecard before the payroll cut-off date."
)


def dry_run_requests(scenario_id: str, decision_action: str, max_output_tokens: int):
    """The requests the LLM nodes would send for the scenario, built with the nodes' own
    functions; None for a clean week. Passages are taken from the pure chunker by key, which is
    exactly the set the retrieve node sends (the finding's own sections and the deal memo)."""
    from payroll_triage.corpus.render import render_agreement
    from payroll_triage.db.seed import all_deal_memos
    from payroll_triage.engine import detect
    from payroll_triage.graph import prompts
    from payroll_triage.graph.execute import MESSAGE_ACTIONS
    from payroll_triage.graph.nodes import build_case, build_request
    from payroll_triage.params import get_parameters
    from payroll_triage.retrieval.chunker import build_corpus
    from payroll_triage.runtime import demo_clock

    params = get_parameters()
    clock = demo_clock()
    memos = all_deal_memos()
    tc = _scenario_timecard(scenario_id)
    memo = memos[tc.deal_memo_id]
    det = detect(
        tc, memo, params, clock.as_of, clock.payroll_run_date, clock.holidays, clock.work_day_type
    )
    if not det.has_findings:
        return None
    findings = [f.to_dict() for f in det.findings]
    case = build_case(tc, memo, findings, clock.payroll_run_date, params.agreement.version)
    chunks = [c.to_dict() for c in build_corpus(params, memos, render_agreement(params))]
    passages = prompts.passages_for_model(findings, chunks, memo.id)

    requests = [
        build_request(
            "explain_propose",
            prompts.explain_propose_prompt(case, findings, passages, det.policy_action),
            prompts.ExplainProposeOutput,
            case["case_id"],
            findings,
            max_output_tokens,
        )
    ]
    if decision_action in MESSAGE_ACTIONS:
        key = findings[0]["citation_keys"][0]
        requests.append(
            build_request(
                "draft",
                prompts.draft_prompt(
                    case,
                    findings,
                    passages,
                    det.policy_action,
                    decision_action,
                    PLACEHOLDER_EXPLANATION.replace("KEY", key),
                    PLACEHOLDER_CORRECTION if decision_action == "return" else None,
                ),
                prompts.DraftOutput,
                case["case_id"],
                findings,
                max_output_tokens,
            )
        )
    return det.policy_action, [p["citation_key"] for p in passages], requests


def dry_run(scenario_id: str, decision_action: str, max_output_tokens: int) -> dict[str, Any]:
    """Estimate input tokens per call and per case; no database, no key, no provider call."""
    from payroll_triage.tokens import CHAT_OVERHEAD_TOKENS, ENCODING, estimate_request

    built = dry_run_requests(scenario_id, decision_action, max_output_tokens)
    if built is None:
        return {"scenario": scenario_id, "clean": True, "llm_calls": 0, "input_tokens": 0}
    policy_action, passage_keys, requests = built
    calls = [{"node": r.schema_name, **estimate_request(r).to_dict()} for r in requests]
    total_in = sum(c["input_tokens"] for c in calls)
    return {
        "scenario": scenario_id,
        "decision": decision_action,
        "policy_action": policy_action,
        "encoding": ENCODING,
        "chat_overhead_per_call": CHAT_OVERHEAD_TOKENS,
        "passages_sent": passage_keys,
        "llm_calls": len(calls),
        "per_call": calls,
        "input_tokens_per_case": total_in,
        "output_cap_per_case": sum(c["max_output_tokens"] for c in calls),
        "note": "input tokens estimated offline; output tokens (including reasoning) are known "
        "only from the provider; the draft input uses a placeholder explanation",
    }


def print_dry_run(report: dict[str, Any]) -> None:
    _p(f"dry run {report['scenario']} (no provider call)", report)
    if not report.get("clean"):
        print(
            f"\nESTIMATED INPUT TOKENS PER CASE ({report['scenario']}, {report['decision']}): "
            f"{report['input_tokens_per_case']} over {report['llm_calls']} calls "
            + ", ".join(f"{c['node']} {c['input_tokens']}" for c in report["per_call"])
        )
