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
    # retrieve
    chunks: list[dict[str, Any]]
    # llm outputs (stored as suggestions, never as decisions)
    explanation: dict[str, Any] | None
    proposal: dict[str, Any] | None
    draft: dict[str, Any] | None
    suggestion_ids: dict[str, int]
    llm_calls: list[dict[str, Any]]
    # validate / review
    validation: dict[str, Any] | None
    review_reason: str | None
    status: str
    route: str
    # human checkpoint and after
    decision: dict[str, Any] | None
    execution: dict[str, Any] | None
    audit_ids: list[int]
