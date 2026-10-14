"""Graph nodes (ADR-018). Code nodes: detect, retrieve, validate, needs_human_review,
human_checkpoint, validate_draft, message_checkpoint, execute, audit. LLM nodes (through the
adapter only): explain_propose before the human checkpoint, draft after it, only for the action
the human chose (return or escalate).

Any LLM failure, unparsable output, invalid citation, bracketed pseudo-reference, stray number
or proposal mismatch routes the case to needs human review: the case is shown with facts only
and the reason; no template ever replaces the model's text (constraint 7).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from dataclasses import field as dc_field
from decimal import Decimal, InvalidOperation
from typing import Any

from langgraph.types import interrupt
from pydantic import BaseModel, ValidationError

from payroll_triage.corpus.deal_memos import DealMemo
from payroll_triage.db.store import AlreadyExecuted, CaseRecord, CaseStore, case_id_for
from payroll_triage.engine import detect as engine_detect
from payroll_triage.graph import prompts
from payroll_triage.graph.execute import (
    DEFAULT_INTAKE_STATUS,
    MESSAGE_ACTIONS,
    RECIPIENTS,
    message_source,
    plan_execution,
    validate_choice,
    validate_message,
)
from payroll_triage.graph.state import CaseState
from payroll_triage.llm.v1 import LLMAdapter, LLMError, LLMRequest, Message
from payroll_triage.params import RuleParameters
from payroll_triage.retrieval.citations import validate_citations
from payroll_triage.retrieval.search import Retriever
from payroll_triage.timecards import DEFAULT_WORK_DAY_TYPE, Timecard

SYSTEM_ACTOR = "system"
NEEDS_HUMAN_REVIEW = "needs_human_review"


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


def build_case(
    tc: Timecard,
    memo: DealMemo,
    findings: list[dict[str, Any]],
    payroll_run_date: dt.date,
    version: str,
) -> dict[str, Any]:
    """The case context for the prompts and the approver (names, dates, ids; no computation)."""
    day_dates = sorted({f["day_date"] for f in findings if f.get("day_date")})
    days = {d.date.isoformat(): d.to_dict() for d in tc.days if d.date.isoformat() in day_dates}
    return {
        "case_id": case_id_for(tc.id),
        "timecard_id": tc.id,
        "employee_name": tc.employee_name,
        "employee_id": tc.employee_id,
        "occupation_title": memo.occupation_title,
        "occupation_code": memo.occupation_code,
        "department": tc.department,
        "deal_memo_id": memo.id,
        "week_ending": tc.week_ending.isoformat(),
        "payroll_cutoff_date": payroll_run_date.isoformat(),
        "version_in_force": version,
        "days_with_findings": days,
    }


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
        case = build_case(tc, memo, findings, deps.clock.payroll_run_date, version)
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
            "cancelled_rounds": 0,
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
        """Records the full ranked results; only the finding's own sections and the case's deal
        memo are sent to the model (ADR-018)."""
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
        sent = prompts.passages_for_model(
            state["findings"], list(chunks.values()), state["case"]["deal_memo_id"]
        )
        if not sent:
            return {
                "chunks": list(chunks.values()),
                "passage_keys": [],
                "route": "review",
                "review_reason": "retrieval returned no passages",
            }
        return {
            "chunks": list(chunks.values()),
            "passage_keys": [c["citation_key"] for c in sent],
            "route": "ok",
        }

    return retrieve


def _sent_passages(state: CaseState) -> list[dict[str, Any]]:
    by_key = {c["citation_key"]: c for c in state["chunks"]}
    return [by_key[k] for k in state.get("passage_keys", []) if k in by_key]


# ---------- LLM nodes ----------


# The merged call returns two outputs (explanation and proposal) in one object, so its output
# cap is twice the configured one; a cap bounds the output, it is not spent unless used.
OUTPUT_CAP_FACTOR = {"explain_propose": 2, "draft": 1}


def build_request(
    kind: str,
    user_prompt: str,
    output_model: type[BaseModel],
    case_id: str,
    findings: list[dict[str, Any]],
    max_output_tokens: int,
) -> LLMRequest:
    """The exact request an LLM node sends (also used by the offline dry run, ADR-019)."""
    return LLMRequest(
        system=prompts.SYSTEM_PROMPT,
        messages=(Message("user", user_prompt),),
        response_schema=prompts.strict_schema(output_model),
        schema_name=kind,
        max_output_tokens=max_output_tokens * OUTPUT_CAP_FACTOR.get(kind, 1),
        metadata={
            "case_id": case_id,
            "node": kind,
            "rule_ids": ",".join(f["rule_id"] for f in findings),
            "prompt_version": prompts.PROMPT_VERSION,
        },
    )


def _call(
    deps: Deps,
    state: CaseState,
    kind: str,
    user_prompt: str,
    output_model: type[BaseModel],
) -> tuple[BaseModel | None, Any, dict[str, Any], str | None]:
    """One structured LLM call. Returns (parsed model, response, call summary, error reason)."""
    request = build_request(
        kind,
        user_prompt,
        output_model,
        state["case_id"],
        state["findings"],
        deps.max_output_tokens,
    )
    try:
        response = deps.adapter.complete(request)
    except LLMError as exc:
        return None, None, {"node": kind, "error": str(exc)}, f"{kind}: LLM call failed: {exc}"
    summary = {"node": kind, **response.summary(), "rate_limit": response.rate_limit}
    try:
        parsed = output_model.model_validate(response.parsed or {})
    except ValidationError as exc:
        reason = f"{kind}: output did not match the schema: {exc.errors()[0]['msg']}"
        return None, response, summary, reason
    return parsed, response, summary, None


def _record(
    deps: Deps, state: CaseState, contents: dict[str, dict[str, Any]], response, summary
) -> dict[str, int]:
    ids, audit_id = deps.store.record_llm_output(
        state["case_id"],
        contents,
        response.provider,
        response.model,
        response.adapter_version,
        _llm_actor(deps.adapter),
        summary,
    )
    summary["suggestion_ids"] = ids
    summary["audit_id"] = audit_id
    return ids


def make_explain_propose(deps: Deps):
    def explain_propose(state: CaseState) -> CaseState:
        parsed, response, summary, reason = _call(
            deps,
            state,
            "explain_propose",
            prompts.explain_propose_prompt(
                state["case"], state["findings"], _sent_passages(state), state["policy_action"]
            ),
            prompts.ExplainProposeOutput,
        )
        calls = [*state.get("llm_calls", []), summary]
        if reason or parsed is None:
            return {
                "explanation": None,
                "proposal": None,
                "llm_calls": calls,
                "route": "review",
                "review_reason": reason,
            }
        content = parsed.model_dump(mode="json")
        ids = _record(
            deps,
            state,
            {"explain": content["explanation"], "propose": content["proposal"]},
            response,
            summary,
        )
        return {
            "explanation": content["explanation"],
            "proposal": content["proposal"],
            "llm_calls": calls,
            "suggestion_ids": {**state.get("suggestion_ids", {}), **ids},
            "route": "ok",
        }

    return explain_propose


def make_draft(deps: Deps):
    def draft(state: CaseState) -> CaseState:
        decision = state["decision"] or {}
        analysis_valid = bool((state.get("validation") or {}).get("valid"))
        explanation = (state.get("explanation") or {}).get("explanation")
        correction = (state.get("proposal") or {}).get("requested_correction")
        parsed, response, summary, reason = _call(
            deps,
            state,
            "draft",
            prompts.draft_prompt(
                state["case"],
                state["findings"],
                _sent_passages(state),
                state["policy_action"],
                decision["action"],
                explanation if analysis_valid else None,
                correction if analysis_valid else None,
            ),
            prompts.DraftOutput,
        )
        calls = [*state.get("llm_calls", []), summary]
        if reason or parsed is None:
            return {"draft": None, "draft_error": reason, "llm_calls": calls}
        content = parsed.model_dump(mode="json")
        ids = _record(deps, state, {"draft": content}, response, summary)
        return {
            "draft": content,
            "draft_error": None,
            "llm_calls": calls,
            "suggestion_ids": {**state.get("suggestion_ids", {}), **ids},
        }

    return draft


# ---------- validation helpers ----------

_IDENTIFIER = re.compile(r"\b[A-Z]{2,8}-[0-9][0-9.]*(?:-[A-Z0-9.-]+)?\b|\b[A-Z]{2,8}-[A-Z]\b")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_KEY = r"[A-Z]{2,8}-\d{4}\.\d+-(?:\d{1,2}\.\d{1,2}|SCH-[A-Z])|DM-[A-Z0-9]+"
_KEY_RE = re.compile(_KEY)
# A key in prose must stand alone: "CGMA-2026.1-8.21" is not key 8.2 and "XDM-01" is not DM-01.
# A sentence-final period after the key is allowed.
_KEY_IN_PROSE = re.compile(r"(?<![\w.-])(?:" + _KEY + r")(?![\w-]|\.\d)")
_LOOKS_LIKE_KEY = re.compile(r"(?<![\w.-])[A-Z]{2,8}-\d{4}\.\d+-[\w.-]*\w|(?<![\w.-])DM-\w+")
_BRACKETED = re.compile(r"\[([^\[\]]*)\]")
_KEY_LIST_SEPARATOR = re.compile(r"[\s,;]+")


def _bracket_keys(content: str) -> list[str] | None:
    """The citation keys inside one bracket, or None when it holds anything else."""
    parts = [p for p in _KEY_LIST_SEPARATOR.split(content.strip()) if p]
    if parts and all(_KEY_RE.fullmatch(p) for p in parts):
        return parts
    return None


def pseudo_references(text: str) -> list[str]:
    """Bracketed text that is not a citation key, for example "[MEAL_PERIOD facts: ...]"
    (P1.I2b.S2). Brackets holding one or more citation keys are citations, not pseudo-references;
    whether those keys are valid is the citation validator's job."""
    return [f"[{m}]" for m in _BRACKETED.findall(text) if _bracket_keys(m) is None]


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
    """Numbers the model may write (ADR-008): the facts' values, the case context shown to it
    and the passages it cited plus the finding's own sections."""
    shown = prompts.case_context(state["case"]) if state["case"] else {}
    text = json.dumps([f["facts"] for f in state["findings"]]) + json.dumps(shown)
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
        text = output.get(field) or ""
        for content in _BRACKETED.findall(text):
            keys.extend(_bracket_keys(content) or ())
        # A key written in prose without brackets is a citation too and is validated the same
        # way (exists, sent to the model, version, the case's deal memo).
        keys.extend(_KEY_IN_PROSE.findall(text))
        # A key-shaped token that is not a well-formed key is kept as written, so the citation
        # validator reports it as unknown instead of it passing unseen.
        keys.extend(t for t in _LOOKS_LIKE_KEY.findall(text) if not _KEY_RE.fullmatch(t))
    return list(dict.fromkeys(keys))


def _check_output(
    deps: Deps,
    state: CaseState,
    kind: str,
    output: dict[str, Any] | None,
    fields: tuple[str, ...],
    required: list[str],
) -> tuple[dict[str, Any], list[str]]:
    """Citations (provided, existing, version, deal memo, required), pseudo-references and stray
    numbers for one output. Returns (detail, problems)."""
    keys = cited_keys(output, *fields)
    result = validate_citations(
        keys,
        deps.retriever.get,
        version_in_force=state["version_in_force"],
        deal_memo_id=state["case"]["deal_memo_id"],
        required_keys=required,
        provided_keys=state.get("passage_keys", []),
    )
    text = " ".join((output or {}).get(f) or "" for f in fields)
    stray = stray_numbers(text, state, keys)
    pseudo = pseudo_references(text)
    problems: list[str] = []
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
    if pseudo:
        problems.append(f"{kind}: bracketed text that is not a citation key: {pseudo}")
    if stray:
        problems.append(f"{kind}: numbers not in the facts or passages: {stray}")
    detail = {**result.to_dict(), "pseudo_references": pseudo, "stray_numbers": stray}
    return detail, problems


# ---------- validate (explanation and proposal) ----------


def governing_keys(state: CaseState) -> list[str]:
    """The governing section of every finding: the explanation and the drafted message must cite
    each of them (ADR-003 tier 1)."""
    return list(
        dict.fromkeys(f["citation_keys"][0] for f in state["findings"] if f["citation_keys"])
    )


def make_validate(deps: Deps):
    def validate(state: CaseState) -> CaseState:
        problems: list[str] = []
        detail: dict[str, Any] = {}
        # The explanation must cite the governing section of every finding (ADR-003 tier 1).
        required = governing_keys(state)

        for kind, key, fields in (
            ("explain", "explanation", ("explanation",)),
            ("propose", "proposal", ("justification", "requested_correction")),
        ):
            part_detail, part_problems = _check_output(
                deps, state, kind, state.get(key), fields, required if kind == "explain" else []
            )
            detail[kind] = part_detail
            problems.extend(part_problems)
            sid = state.get("suggestion_ids", {}).get(kind)
            if sid is not None:
                deps.store.set_suggestion_validation(
                    sid, "invalid" if part_problems else "valid", part_detail
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
        deps.store.set_case_status(state["case_id"], NEEDS_HUMAN_REVIEW, reason)
        deps.store.add_audit(
            state["case_id"],
            "review",
            SYSTEM_ACTOR,
            {"reason": reason, "facts_only": True, "findings": state["findings"]},
        )
        return {"status": NEEDS_HUMAN_REVIEW, "review_reason": reason}

    return needs_human_review


# ---------- human checkpoint (interrupt 1) ----------


def make_human_checkpoint(deps: Deps):
    def human_checkpoint(state: CaseState) -> CaseState:
        payload = {
            "case_id": state["case_id"],
            "status": state["status"],
            "policy_action": state["policy_action"],
            "review_reason": state.get("review_reason"),
            "needs": "the action (approve, return, escalate) and the actor; for return and "
            "escalate the message is drafted next and confirmed by the same actor",
        }
        choice = validate_choice(dict(interrupt(payload)))
        case = deps.store.get_case(state["case_id"])
        status_at_checkpoint = case.status if case is not None else state["status"]
        ids = {k: v for k, v in state.get("suggestion_ids", {}).items() if k != "draft"}
        update: CaseState = {
            "decision": choice,
            "status_at_checkpoint": status_at_checkpoint,
            "draft": None,
            "draft_error": None,
            "draft_validation": None,
            "suggestion_ids": ids,
        }
        if choice["action"] in MESSAGE_ACTIONS:
            # The only write of this node, after the interrupt (ADR-018, second PRE review).
            deps.store.add_audit(
                state["case_id"],
                "decision",
                choice["actor"],
                {
                    "stage": "action_chosen",
                    "action": choice["action"],
                    "policy_action": state["policy_action"],
                    "case_status_before": status_at_checkpoint,
                },
            )
        return update

    return human_checkpoint


# ---------- validate draft ----------


def make_validate_draft(deps: Deps):
    def validate_draft(state: CaseState) -> CaseState:
        decision = state["decision"] or {}
        output = state.get("draft")
        if output is None:
            problems = [state.get("draft_error") or "draft: no output"]
            detail: dict[str, Any] = {}
        else:
            detail, problems = _check_output(
                deps, state, "draft", output, ("subject", "body"), governing_keys(state)
            )
            if output.get("for_action") != decision["action"]:
                problems.append(
                    f"draft: written for {output.get('for_action')!r}, the approver chose "
                    f"{decision['action']!r}"
                )
            if output.get("recipient_role") not in RECIPIENTS[decision["action"]]:
                problems.append(
                    f"draft: recipient {output.get('recipient_role')!r} does not fit a "
                    f"{decision['action']}"
                )
            sid = state.get("suggestion_ids", {}).get("draft")
            if sid is not None:
                deps.store.set_suggestion_validation(
                    sid, "invalid" if problems else "valid", detail
                )
        validation = {"valid": not problems, "problems": problems, "detail": detail}
        if not problems:
            return {"draft_validation": validation}
        # Constraint 7: the case is marked needs human review; the human writes the message or
        # cancels. Once set, the status stays until execution (ADR-018, second PRE review).
        draft_reason = "; ".join(p if p.startswith("draft") else f"draft: {p}" for p in problems)
        case = deps.store.get_case(state["case_id"])
        previous = case.review_reason if case is not None else None
        reason = f"{previous}; {draft_reason}" if previous else draft_reason
        deps.store.set_case_status(state["case_id"], NEEDS_HUMAN_REVIEW, reason)
        deps.store.add_audit(
            state["case_id"],
            "review",
            SYSTEM_ACTOR,
            {"output": "draft", "reason": draft_reason, "facts_only": True},
        )
        return {
            "draft_validation": validation,
            "status": NEEDS_HUMAN_REVIEW,
            "review_reason": reason,
        }

    return validate_draft


def draft_is_valid(state: CaseState) -> bool:
    return bool((state.get("draft_validation") or {}).get("valid"))


# ---------- message checkpoint (interrupt 2) ----------


def make_message_checkpoint(deps: Deps):
    def message_checkpoint(state: CaseState) -> CaseState:
        decision = state["decision"] or {}
        valid = draft_is_valid(state)
        payload = {
            "case_id": state["case_id"],
            "chosen_action": decision.get("action"),
            "draft": state.get("draft") if valid else None,
            "draft_valid": valid,
            "needs": "the confirmed message from the actor who chose the action, or a cancel",
        }
        reply = validate_message(dict(interrupt(payload)), decision)
        if reply["cancel"]:
            ids = {k: v for k, v in state.get("suggestion_ids", {}).items() if k != "draft"}
            # The only write of this node, after the interrupt.
            deps.store.add_audit(
                state["case_id"],
                "decision",
                reply["actor"],
                {
                    "stage": "message_cancelled",
                    "action": decision.get("action"),
                    "chosen_by": decision.get("actor"),
                    "draft_suggestion_id": state.get("suggestion_ids", {}).get("draft"),
                    "draft_valid": valid,
                },
            )
            return {
                "decision": None,
                "draft": None,
                "draft_error": None,
                "draft_validation": None,
                "suggestion_ids": ids,
                "cancelled_rounds": state.get("cancelled_rounds", 0) + 1,
                "route": "cancel",
            }
        draft_body = (state.get("draft") or {}).get("body") if valid else None
        return {
            "decision": {
                **decision,
                "message": reply["message"],
                "recipient_role": reply["recipient_role"],
                "message_source": message_source(reply["message"], draft_body),
            },
            "route": "confirmed",
        }

    return message_checkpoint


# ---------- execute and audit ----------


def _executed_entry(state: CaseState, decision: dict[str, Any]) -> dict[str, Any]:
    original_draft = (state.get("draft") or {}).get("body")
    return {
        "stage": "executed",
        "action": decision["action"],
        "message": decision.get("message"),
        "recipient_role": decision.get("recipient_role"),
        "original_draft": original_draft,
        "original_draft_valid": draft_is_valid(state) if original_draft else None,
        "message_edited": decision.get("message_source") == "draft_edited",
        "message_source": decision.get("message_source"),
        "policy_action": state["policy_action"],
        "proposed_action": (state.get("proposal") or {}).get("proposed_action"),
        "cancelled_rounds": state.get("cancelled_rounds", 0),
        "case_status_before": state.get("status_at_checkpoint"),
    }


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
        # The `executed` audit entry and the execution entry are written in the same transaction
        # as the effects, so a retry after a lost checkpoint can never leave an execution
        # without its audit record (ADR-018).
        plan = replace(plan, decision_audit=_executed_entry(state, decision))
        try:
            effects = deps.store.apply_execution(
                plan
            )  # decision, effects and audit, one transaction
        except AlreadyExecuted:
            case = deps.store.get_case(state["case_id"])
            status = case.status if case is not None else state.get("status")
            return {"execution": {"already_executed": True, "case_status": status}}
        return {"execution": effects, "status": effects["case_status"]}

    return execute


def make_audit(deps: Deps):
    def audit(state: CaseState) -> CaseState:
        decision = state["decision"]
        assert decision is not None
        actor = decision["actor"]
        execution = state.get("execution") or {}
        if execution.get("already_executed"):
            ids = [
                deps.store.add_audit(
                    state["case_id"],
                    "decision",
                    actor,
                    {"stage": "duplicate_attempt", "action": decision["action"], **execution},
                )
            ]
            return {"audit_ids": [*state.get("audit_ids", []), *ids]}
        # The executed and execution entries were written with the effects (execute node).
        return {"audit_ids": [*state.get("audit_ids", []), *execution.get("audit_ids", [])]}

    return audit
