"""In-memory case store and retriever with the same interfaces as the PostgreSQL ones."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import replace
from typing import Any

from payroll_triage.corpus.deal_memos import DealMemo
from payroll_triage.db.store import CaseRecord, ExecutionPlan
from payroll_triage.retrieval.chunker import Chunk
from payroll_triage.retrieval.search import RankedChunk, combine
from payroll_triage.timecards import Timecard


def _plain(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


class MemoryStore:
    def __init__(self, timecards: dict[str, Timecard], memos: dict[str, DealMemo]) -> None:
        self.timecards = dict(timecards)
        self.memos = dict(memos)
        self.cases: dict[str, CaseRecord] = {}
        self.suggestions: list[dict[str, Any]] = []
        self.audit: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        self.premium_lines: list[dict[str, Any]] = []
        self.return_messages: list[dict[str, Any]] = []
        self.escalations: list[dict[str, Any]] = []

    def get_timecard(self, timecard_id: str) -> Timecard | None:
        return self.timecards.get(timecard_id)

    def get_deal_memo(self, memo_id: str) -> DealMemo | None:
        return self.memos.get(memo_id)

    def list_timecards(self, week_ending: dt.date, status: str) -> list[Timecard]:
        return sorted(
            (
                t
                for t in self.timecards.values()
                if t.week_ending == week_ending and t.status == status
            ),
            key=lambda t: t.id,
        )

    def get_case(self, case_id: str) -> CaseRecord | None:
        return self.cases.get(case_id)

    def get_case_by_timecard(self, timecard_id: str) -> CaseRecord | None:
        return next((c for c in self.cases.values() if c.timecard_id == timecard_id), None)

    def list_queue(self) -> list[CaseRecord]:
        open_cases = [
            c
            for c in self.cases.values()
            if c.status in ("awaiting_decision", "needs_human_review")
        ]
        return sorted(open_cases, key=lambda c: (-c.priority_score, c.week_ending, c.id))

    def create_case(self, case: CaseRecord) -> None:
        self.cases[case.id] = replace(case, created_at=dt.datetime.now(dt.UTC))

    def set_case_status(self, case_id: str, status: str, review_reason: str | None) -> None:
        self.cases[case_id] = replace(
            self.cases[case_id], status=status, review_reason=review_reason
        )

    def add_suggestion(self, case_id, kind, content, provider, model, adapter_version) -> int:
        self.suggestions.append(
            {
                "id": len(self.suggestions) + 1,
                "case_id": case_id,
                "kind": kind,
                "content": _plain(content),
                "provider": provider,
                "model": model,
                "adapter_version": adapter_version,
                "validation_status": "not_validated",
                "validation_detail": None,
            }
        )
        return self.suggestions[-1]["id"]

    def set_suggestion_validation(self, suggestion_id: int, status: str, detail) -> None:
        row = self.suggestions[suggestion_id - 1]
        row["validation_status"] = status
        row["validation_detail"] = _plain(detail)

    def list_suggestions(self, case_id: str) -> list[dict[str, Any]]:
        return [s for s in self.suggestions if s["case_id"] == case_id]

    def add_audit(self, case_id: str, entry_kind: str, actor: str, payload) -> int:
        self.audit.append(
            {
                "id": len(self.audit) + 1,
                "case_id": case_id,
                "entry_kind": entry_kind,
                "actor": actor,
                "payload": _plain(payload),
                "created_at": dt.datetime.now(dt.UTC).isoformat(),
            }
        )
        return self.audit[-1]["id"]

    def list_audit(self, case_id: str) -> list[dict[str, Any]]:
        return [a for a in self.audit if a["case_id"] == case_id]

    def apply_execution(self, plan: ExecutionPlan) -> dict[str, Any]:
        effects: dict[str, Any] = {"action": plan.action, "actor": plan.actor}
        self.decisions.append(
            {
                "id": len(self.decisions) + 1,
                "case_id": plan.case_id,
                "actor": plan.actor,
                "action": plan.action,
                "message": plan.decision_message,
            }
        )
        effects["decision_id"] = self.decisions[-1]["id"]
        if plan.timecard_status_after:
            tc = self.timecards[plan.timecard_id]
            self.timecards[plan.timecard_id] = replace(tc, status=plan.timecard_status_after)
            effects["timecard_status"] = plan.timecard_status_after
        if plan.premium_lines:
            ids = []
            for line in plan.premium_lines:
                self.premium_lines.append(
                    {"case_id": plan.case_id, **line.__dict__, "created_by": plan.actor}
                )
                ids.append(len(self.premium_lines))
            effects["premium_line_ids"] = ids
            effects["premium_total_usd"] = f"{sum(x.amount_usd for x in plan.premium_lines):.2f}"
        if plan.return_message is not None:
            self.return_messages.append(
                {"case_id": plan.case_id, "body": plan.return_message, "sent_by": plan.actor}
            )
            effects["return_message_id"] = len(self.return_messages)
        if plan.escalation_note is not None:
            self.escalations.append({"case_id": plan.case_id, "note": plan.escalation_note})
            effects["escalation_id"] = len(self.escalations)
            effects["escalation_note_source"] = plan.escalation_note_source
        self.cases[plan.case_id] = replace(self.cases[plan.case_id], status=plan.case_status_after)
        effects["case_status"] = plan.case_status_after
        return effects


class MemoryRetriever:
    """Keyword-overlap ranking over the chunks; good enough to exercise the graph."""

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = {c.citation_key: c for c in chunks}

    def get(self, citation_key: str) -> Chunk | None:
        return self.chunks.get(citation_key)

    def _rank(self, query: str) -> list[Chunk]:
        words = {w.lower().strip(".,;:") for w in query.split()}
        scored = []
        for c in self.chunks.values():
            text = c.text.lower()
            score = sum(1 for w in words if w and w in text)
            scored.append((score, c.citation_key, c))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [c for _, _, c in scored]

    def search(self, query: str, *, top_k: int = 6) -> list[RankedChunk]:
        ranked = self._rank(query)
        return combine(ranked[:top_k], ranked[:top_k], top_k)
