"""Graph nodes. Code nodes: detect, retrieve, validate, needs_human_review, human_checkpoint,
execute, audit. LLM nodes: explain, propose, draft (through the adapter only).

Any LLM failure, unparsable output, invalid citation, stray number or proposal
mismatch sets `route = "review"`: the case is shown with facts only and the
reason; no template ever replaces the model's text (constraint 7).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field as dc_field
from decimal import Decimal, InvalidOperation
from typing import Any

from langgraph.types import interrupt
from pydantic import BaseModel, ValidationError

from payroll_triage.db.store import CaseRecord, CaseStore, case_id_for
from payroll_triage.engine import detect as engine_detect
from payroll_triage.graph import prompts
from payroll_triage.graph.execute import (
    DEFAULT_INTAKE_STATUS,
    plan_execution,
    validate_decision,
)
from payroll_triage.graph.state import CaseState
from payroll_triage.llm.v1 import LLMAdapter, LLMError, LLMRequest, Message
from payroll_triage.params import RuleParameters
from payroll_triage.retrieval.citations import validate_citations
from payroll_triage.retrieval.search import Retriever
from payroll_triage.timecards import DEFAULT_WORK_DAY_TYPE

SYSTEM_ACTOR = "system"


@dataclass(frozen=True)
class Clock:
    """The queue's notion of today and the next payroll run (demo values from the catalog)."""

    as_of: dt.date
    payroll_run_date: dt.date
    holidays: tuple[dt.date, ...] = ()
    work_day_type: str = DEFAULT_WORK_DAY_TYPE
    intake_status: str = DEFAULT_INTAKE_STATUS
    timecard_status_after: dict[str, str | None] = dc_field(default_factory=dict)


@dataclass
class Deps:
    store: CaseStore
    retriever: Retriever
    adapter: LLMAdapter
    params: RuleParameters
    clock: Clock
    max_output_tokens: int = 1200


def _llm_actor(adapter: LLMAdapter) -> str:
    return f"llm:{adapter.provider}/{adapter.model}"


# ---------- detect ----------


def make_detect(deps: Deps):
    def detect(state: CaseState) -> CaseState:
        tc = deps.store.get_timecard(state["timecard_id"])
        if tc is None:
            raise KeyError(f"timecard {state['timecard_id']} not found")
        memo = deps.store.get_deal_memo(tc.deal_memo_id)
        if memo is None:
            raise KeyError(f"deal memo {tc.deal_memo_id} not found")
        det = engine_detect(
            tc,
            memo,
            deps.params,
            deps.clock.as_of,
            deps.clock.payroll_run_date,
            deps.clock.holidays,
            deps.clock.work_day_type,
        )
        if not det.has_findings:
            return {"findings": [], "policy_action": "none", "route": "clean", "status": "clean"}
        case_id = case_id_for(tc.id)
        version = deps.params.agreement.version
        findings = [f.to_dict() for f in det.findings]
        if deps.store.get_case(case_id) is None:
            deps.store.create_case(
                CaseRecord(
                    id=case_id,
                    timecard_id=tc.id,
                    deal_memo_id=memo.id,
                    week_ending=tc.week_ending,
                    findings=findings,
                    policy_action=det.policy_action,
                    amount_usd=det.amount_usd,
                    priority_score=det.priority_score,
                    status="detected",
                    thread_id=case_id,
                )
            )
        day_dates = sorted({f["day_date"] for f in findings if f.get("day_date")})
        days = {d.date.isoformat(): d.to_dict() for d in tc.days if d.date.isoformat() in day_dates}
        case = {
            "case_id": case_id,
            "timecard_id": tc.id,
            "employee_name": tc.employee_name,
            "employee_id": tc.employee_id,
            "occupation_title": memo.occupation_title,
            "occupation_code": memo.occupation_code,
            "department": tc.department,
            "deal_memo_id": memo.id,
            "week_ending": tc.week_ending.isoformat(),
            "payroll_cutoff_date": deps.clock.payroll_run_date.isoformat(),
            "version_in_force": version,
            "days_with_findings": days,
        }
        return {
            "case_id": case_id,
            "case": case,
            "findings": findings,
            "policy_action": det.policy_action,
            "amount_usd": f"{det.amount_usd:.2f}",
            "priority_score": det.priority_score,
            "version_in_force": version,
            "status": "detected",
            "route": "findings",
            "llm_calls": [],
            "suggestion_ids": {},
            "audit_ids": [],
        }

    return detect


# ---------- retrieve ----------


def retrieval_query(finding: dict[str, Any], params: RuleParameters) -> str:
    ref = params.rule(finding["rule_id"])
    facts = finding.get("facts", {})
    parts = [ref.title, f"section {ref.section}"]
    if finding["rule_id"] == "MEAL_PERIOD":
        parts.append("first meal period deadline after call")
        if facts.get("is_late"):
            parts.append("meal penalty increments Schedule B")
        if facts.get("is_short"):
            parts.append("meal shorter than the minimum duration returned for correction")
    return " ".join(parts)


def make_retrieve(deps: Deps):
    def retrieve(state: CaseState) -> CaseState:
        chunks: dict[str, dict[str, Any]] = {}
        for finding in state["findings"]:
            for ranked in deps.retriever.search(retrieval_query(finding, deps.params)):
                chunks.setdefault(ranked.chunk.citation_key, ranked.to_dict())
            for key in finding["citation_keys"]:
                chunk = deps.retriever.get(key)
                if chunk is not None:
                    chunks.setdefault(key, {**chunk.to_dict(), "score": None})
        memo_chunk = deps.retriever.get(state["case"]["deal_memo_id"])
        if memo_chunk is not None:
            chunks.setdefault(memo_chunk.citation_key, {**memo_chunk.to_dict(), "score": None})
        if not chunks:
            return {
                "chunks": [],
                "route": "review",
                "review_reason": "retrieval returned no passages",
            }
        return {"chunks": list(chunks.values()), "route": "ok"}

    return retrieve


# ---------- LLM nodes ----------


def _call(
    deps: Deps,
    state: CaseState,
    kind: str,
    user_prompt: str,
    output_model: type[BaseModel],
) -> tuple[dict[str, Any] | None, dict[str, Any], str | None]:
    """One structured LLM call. Returns (parsed output, call summary, error reason)."""
    request = LLMRequest(
        system=prompts.SYSTEM_PROMPT,
        messages=(Message("user", user_prompt),),
        response_schema=prompts.strict_schema(output_model),
        schema_name=kind,
        max_output_tokens=deps.max_output_tokens,
        metadata={
            "case_id": state["case_id"],
            "node": kind,
            "rule_ids": ",".join(f["rule_id"] for f in state["findings"]),
            "prompt_version": prompts.PROMPT_VERSION,
        },
    )
    try:
        response = deps.adapter.complete(request)
    except LLMError as exc:
        return None, {"node": kind, "error": str(exc)}, f"{kind}: LLM call failed: {exc}"
    summary = {"node": kind, **response.summary(), "rate_limit": response.rate_limit}
    try:
        parsed = output_model.model_validate(response.parsed or {})
    except ValidationError as exc:
        return None, summary, f"{kind}: output did not match the schema: {exc.errors()[0]['msg']}"
    content = parsed.model_dump(mode="json")
    suggestion_id = deps.store.add_suggestion(
        state["case_id"],
        kind,
        content,
        response.provider,
        response.model,
        response.adapter_version,
    )
    audit_id = deps.store.add_audit(
        state["case_id"],
        "suggestion",
        _llm_actor(deps.adapter),
        {"kind": kind, "suggestion_id": suggestion_id, "content": content, "llm": summary},
    )
    summary["suggestion_id"] = suggestion_id
    summary["audit_id"] = audit_id
    return content, summary, None


def make_explain(deps: Deps):
    def explain(state: CaseState) -> CaseState:
        content, summary, reason = _call(
            deps,
            state,
            "explain",
            prompts.explain_prompt(state["case"], state["findings"], state["chunks"]),
            prompts.ExplainOutput,
        )
        calls = [*state.get("llm_calls", []), summary]
        if reason:
            return {
                "explanation": None,
                "llm_calls": calls,
                "route": "review",
                "review_reason": reason,
            }
        ids = {**state.get("suggestion_ids", {}), "explain": summary["suggestion_id"]}
        return {"explanation": content, "llm_calls": calls, "suggestion_ids": ids, "route": "ok"}

    return explain


def make_propose(deps: Deps):
    def propose(state: CaseState) -> CaseState:
        content, summary, reason = _call(
            deps,
            state,
            "propose",
            prompts.propose_prompt(
                state["case"], state["findings"], state["chunks"], state["policy_action"]
            ),
            prompts.ProposeOutput,
        )
        calls = [*state.get("llm_calls", []), summary]
        if reason:
            return {
                "proposal": None,
                "llm_calls": calls,
                "route": "review",
                "review_reason": reason,
            }
        ids = {**state.get("suggestion_ids", {}), "propose": summary["suggestion_id"]}
        return {"proposal": content, "llm_calls": calls, "suggestion_ids": ids, "route": "ok"}

    return propose


def make_draft(deps: Deps):
    def draft(state: CaseState) -> CaseState:
        content, summary, reason = _call(
            deps,
            state,
            "draft",
            prompts.draft_prompt(
                state["case"], state["findings"], state["chunks"], state["proposal"] or {}
            ),
            prompts.DraftOutput,
        )
        calls = [*state.get("llm_calls", []), summary]
        if reason:
            return {"draft": None, "llm_calls": calls, "route": "review", "review_reason": reason}
        ids = {**state.get("suggestion_ids", {}), "draft": summary["suggestion_id"]}
        return {"draft": content, "llm_calls": calls, "suggestion_ids": ids, "route": "ok"}

    return draft


# ---------- validate ----------

_IDENTIFIER = re.compile(r"\b[A-Z]{2,8}-[0-9][0-9.]*(?:-[A-Z0-9.-]+)?\b|\b[A-Z]{2,8}-[A-Z]\b")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_KEY_IN_TEXT = re.compile(
    r"\[([A-Z]{2,8}-\d{4}\.\d+-(?:\d{1,2}\.\d{1,2}|SCH-[A-Z])|DM-[A-Z0-9]+)\]"
)


def numbers_in(text: str) -> set[Decimal]:
    """Numeric tokens in free text. Identifiers (citation keys, DM-01, EMP-1001, TC-..., CASE-...)
    are removed first; dates split into their parts so "2026-03-10" allows 2026, 3 and 10."""
    out: set[Decimal] = set()
    for token in _NUMBER.findall(_IDENTIFIER.sub(" ", text)):
        try:
            out.add(Decimal(token.replace(",", "")))
        except InvalidOperation:
            continue
    return out


def allowed_numbers(state: CaseState, cited: Iterable[str] = ()) -> set[Decimal]:
    """Numbers the model may write (ADR-008): the facts' values, the case context (dates and
    identifiers shown to it) and the passages it cited plus the finding's own sections."""
    text = json.dumps([f["facts"] for f in state["findings"]]) + json.dumps(state["case"])
    keys = set(cited)
    for f in state["findings"]:
        keys.update(f.get("citation_keys", ()))
    for c in state["chunks"]:
        if c["citation_key"] in keys:
            text += " " + c["heading"] + " " + c["body"]
    return numbers_in(text)


def stray_numbers(generated: str, state: CaseState, cited: Iterable[str] = ()) -> list[str]:
    allowed = allowed_numbers(state, cited)
    return sorted(str(n) for n in numbers_in(generated) if n not in allowed)


def cited_keys(output: dict[str, Any] | None, *text_fields: str) -> list[str]:
    if not output:
        return []
    keys = list(output.get("citation_keys") or [])
    for field in text_fields:
        keys.extend(_KEY_IN_TEXT.findall(output.get(field) or ""))
    seen: list[str] = []
    for k in keys:
        if k not in seen:
            seen.append(k)
    return seen


def make_validate(deps: Deps):
    def validate(state: CaseState) -> CaseState:
        problems: list[str] = []
        detail: dict[str, Any] = {}
        # The explanation must cite the governing section of every finding (ADR-003 tier 1).
        required: list[str] = []
        for f in state["findings"]:
            if f["citation_keys"] and f["citation_keys"][0] not in required:
                required.append(f["citation_keys"][0])
        memo_id = state["case"]["deal_memo_id"]
        version = state["version_in_force"]

        for kind, fields in (
            ("explain", ("explanation",)),
            ("propose", ("justification", "requested_correction")),
            ("draft", ("body",)),
        ):
            output = state.get(
                {"explain": "explanation", "propose": "proposal", "draft": "draft"}[kind]
            )
            keys = cited_keys(output, *fields)
            result = validate_citations(
                keys,
                deps.retriever.get,
                version_in_force=version,
                deal_memo_id=memo_id,
                required_keys=required if kind == "explain" else (),
            )
            stray = stray_numbers(
                " ".join((output or {}).get(f) or "" for f in fields), state, keys
            )
            ok = result.valid and not stray
            detail[kind] = {**result.to_dict(), "stray_numbers": stray}
            if not result.valid:
                bad = [c for c in result.checks if c.status != "valid"]
                problems.append(
                    f"{kind}: citations invalid ("
                    + "; ".join(f"{c.key} {c.status}" for c in bad)
                    + (
                        f"; required missing {list(result.required_missing)}"
                        if result.required_missing
                        else ""
                    )
                    + (" no citations" if not result.checks else "")
                    + ")"
                )
            if stray:
                problems.append(f"{kind}: numbers not in the facts or passages: {stray}")
            sid = state.get("suggestion_ids", {}).get(kind)
            if sid is not None:
                deps.store.set_suggestion_validation(
                    sid, "valid" if ok else "invalid", detail[kind]
                )

        proposal = state.get("proposal") or {}
        proposed = proposal.get("proposed_action")
        detail["proposal_matches_policy"] = proposed == state["policy_action"]
        if proposed != state["policy_action"]:
            problems.append(
                f"propose: proposed action {proposed!r} differs from the policy action "
                f"{state['policy_action']!r}"
            )
        validation = {"valid": not problems, "problems": problems, "detail": detail}
        deps.store.add_audit(state["case_id"], "validation", SYSTEM_ACTOR, validation)
        if problems:
            return {
                "validation": validation,
                "route": "review",
                "review_reason": "; ".join(problems),
            }
        deps.store.set_case_status(state["case_id"], "awaiting_decision", None)
        return {"validation": validation, "route": "ok", "status": "awaiting_decision"}

    return validate


# ---------- needs human review ----------


def make_needs_human_review(deps: Deps):
    def needs_human_review(state: CaseState) -> CaseState:
        reason = state.get("review_reason") or "unspecified"
        deps.store.set_case_status(state["case_id"], "needs_human_review", reason)
        deps.store.add_audit(
            state["case_id"],
            "review",
            SYSTEM_ACTOR,
            {"reason": reason, "facts_only": True, "findings": state["findings"]},
        )
        return {"status": "needs_human_review", "review_reason": reason}

    return needs_human_review


# ---------- human checkpoint ----------


def make_human_checkpoint(deps: Deps):
    def human_checkpoint(state: CaseState) -> CaseState:
        payload = {
            "case_id": state["case_id"],
            "status": state["status"],
            "policy_action": state["policy_action"],
            "review_reason": state.get("review_reason"),
            "needs": "decision with action (approve, return, escalate), actor and, for a return, "
            "the message to send",
        }
        decision = interrupt(payload)
        return {"decision": validate_decision(dict(decision))}

    return human_checkpoint


# ---------- execute and audit ----------


def make_execute(deps: Deps):
    def execute(state: CaseState) -> CaseState:
        decision = state["decision"]
        assert decision is not None
        plan = plan_execution(
            state["case_id"],
            state["case"]["timecard_id"],
            state["findings"],
            decision,
            deps.clock.timecard_status_after or None,
        )
        effects = deps.store.apply_execution(plan)  # decision row and effects, one transaction
        return {"execution": effects, "status": effects["case_status"]}

    return execute


def make_audit(deps: Deps):
    def audit(state: CaseState) -> CaseState:
        decision = state["decision"]
        assert decision is not None
        actor = decision["actor"]
        original_draft = (state.get("draft") or {}).get("body")
        ids = [
            deps.store.add_audit(
                state["case_id"],
                "decision",
                actor,
                {
                    "action": decision["action"],
                    "message": decision.get("message"),
                    "original_draft": original_draft,
                    "message_edited": bool(
                        decision.get("message") and decision.get("message") != original_draft
                    ),
                    "policy_action": state["policy_action"],
                    "proposed_action": (state.get("proposal") or {}).get("proposed_action"),
                    "case_status_before": state.get("status"),
                },
            ),
            deps.store.add_audit(state["case_id"], "execution", actor, state["execution"] or {}),
        ]
        return {"audit_ids": [*state.get("audit_ids", []), *ids]}

    return audit
