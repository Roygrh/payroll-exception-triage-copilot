"""Triage service: runs the graph per case, pauses at the checkpoint, resumes with a decision."""

from __future__ import annotations

import datetime as dt
from typing import Any

from langgraph.types import Command

from payroll_triage.db.store import CaseStore, case_id_for
from payroll_triage.graph.execute import validate_decision
from payroll_triage.graph.nodes import Deps


class CaseNotFound(KeyError):
    pass


class CaseNotWaiting(RuntimeError):
    pass


class TriageService:
    def __init__(self, graph, deps: Deps) -> None:
        self.graph = graph
        self.deps = deps

    @property
    def store(self) -> CaseStore:
        return self.deps.store

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    def run_timecard(self, timecard_id: str) -> dict[str, Any]:
        """Run detect to the human checkpoint (or to the end for a clean week)."""
        existing = self.store.get_case_by_timecard(timecard_id)
        thread_id = case_id_for(timecard_id)
        if existing is not None and existing.status != "detected":
            return {"case_id": existing.id, "status": existing.status, "already_existed": True}
        if existing is not None:
            # A case left in `detected` means a node after detect raised (store, retriever or
            # unexpected error): resume the stored thread from the node that failed.
            result = self.graph.invoke(None, self._config(thread_id))
        else:
            result = self.graph.invoke({"timecard_id": timecard_id}, self._config(thread_id))
        if result.get("route") == "clean":
            return {"case_id": None, "status": "clean", "timecard_id": timecard_id}
        snapshot = self.graph.get_state(self._config(thread_id))
        return {
            "case_id": result["case_id"],
            "status": result.get("status"),
            "review_reason": result.get("review_reason"),
            "checkpoint_id": snapshot.config["configurable"].get("checkpoint_id"),
            "waiting_on": list(snapshot.next),
            "llm_calls": result.get("llm_calls", []),
        }

    def ingest_week(self, week_ending: dt.date, status: str | None = None) -> list[dict]:
        out = []
        status = status or self.deps.clock.intake_status
        for tc in self.store.list_timecards(week_ending, status):
            out.append({"timecard_id": tc.id, **self.run_timecard(tc.id)})
        return out

    def waiting_state(self, case_id: str):
        case = self.store.get_case(case_id)
        if case is None:
            raise CaseNotFound(case_id)
        snapshot = self.graph.get_state(self._config(case.thread_id))
        return case, snapshot

    def decide(self, case_id: str, decision: dict[str, Any]) -> dict[str, Any]:
        # Validate before resuming: an invalid decision must never reach the checkpoint,
        # because a resume value is persisted with the thread even when the node fails.
        clean = validate_decision(decision)
        case, snapshot = self.waiting_state(case_id)
        before = snapshot.config["configurable"].get("checkpoint_id")
        if list(snapshot.next) in (["execute"], ["audit"]):
            # Execution or audit failed after the decision was accepted (the effects are one
            # transaction, so nothing partial exists). Retry with the decision stored in the
            # thread, never a new one; a different submission is refused and the stored
            # decision is reported.
            stored = (snapshot.values or {}).get("decision") or {}
            same = all(stored.get(k) == clean.get(k) for k in ("action", "actor", "message"))
            if not same:
                raise CaseNotWaiting(
                    f"case {case_id} already has a decision by {stored.get('actor')!r} "
                    f"({stored.get('action')!r}) pending execution; resubmit that decision to "
                    "retry it"
                )
            result = self.graph.invoke(None, self._config(case.thread_id))
            retried = True
        elif "human_checkpoint" not in snapshot.next:
            raise CaseNotWaiting(f"case {case_id} is not waiting at the human checkpoint")
        else:
            result = self.graph.invoke(Command(resume=clean), self._config(case.thread_id))
            retried = False
        after = self.graph.get_state(self._config(case.thread_id))
        return {
            "case_id": case_id,
            "status": result.get("status"),
            "execution": result.get("execution"),
            "audit_ids": result.get("audit_ids", []),
            "checkpoint_id_before": before,
            "checkpoint_id_after": after.config["configurable"].get("checkpoint_id"),
            "retried_execution": retried,
        }

    def case_detail(self, case_id: str) -> dict[str, Any]:
        case, snapshot = self.waiting_state(case_id)
        tc = self.store.get_timecard(case.timecard_id)
        values = snapshot.values or {}
        suggestions = self.store.list_suggestions(case_id)
        status_by_kind = {s["kind"]: s["validation_status"] for s in suggestions}
        return {
            "case": case.to_dict(),
            "timecard": tc.to_dict() if tc else None,
            "explanation": values.get("explanation"),
            "proposal": values.get("proposal"),
            "draft": values.get("draft"),
            # Per output: valid, invalid, not_validated (validation never reached) or missing
            # (the LLM step failed). A non-valid output must never be shown as validated.
            "output_status": {
                kind: status_by_kind.get(kind, "missing")
                for kind in ("explain", "propose", "draft")
            },
            "validation": values.get("validation"),
            "review_reason": values.get("review_reason") or case.review_reason,
            "chunks": [
                {k: c[k] for k in ("citation_key", "source_type", "version", "heading")}
                for c in values.get("chunks", [])
            ],
            "decision": values.get("decision"),
            "execution": values.get("execution"),
            "pending_retry": list(snapshot.next) in (["execute"], ["audit"]),
            "checkpoint_id": snapshot.config["configurable"].get("checkpoint_id"),
            "waiting_on": list(snapshot.next),
            "suggestions": suggestions,
        }
