"""Graph state for one exception case (one LangGraph thread per case, ADR-013)."""

from __future__ import annotations

from typing import Any, TypedDict


class CaseState(TypedDict, total=False):
    # input
    timecard_id: str
    # detect
    case_id: str
    case: dict[str, Any]  # context shown to the LLM and the approver (names, dates, ids)
    findings: list[dict[str, Any]]
    policy_action: str
    amount_usd: str
    priority_score: int
    version_in_force: str
    # retrieve: full ranked results (recorded) and the keys of the passages sent to the model
    chunks: list[dict[str, Any]]
    passage_keys: list[str]
    # llm outputs (stored as suggestions, never as decisions)
    explanation: dict[str, Any] | None
    proposal: dict[str, Any] | None
    draft: dict[str, Any] | None  # drafted after the human chose return or escalate (ADR-018)
    draft_error: str | None
    draft_validation: dict[str, Any] | None
    suggestion_ids: dict[str, int]
    llm_calls: list[dict[str, Any]]
    # validate / review
    validation: dict[str, Any] | None
    review_reason: str | None
    status: str
    route: str
    # human checkpoint (interrupt 1), message checkpoint (interrupt 2) and after
    decision: dict[str, Any] | None  # action and actor; then the confirmed message
    status_at_checkpoint: str | None
    cancelled_rounds: int
    execution: dict[str, Any] | None
    audit_ids: list[int]
