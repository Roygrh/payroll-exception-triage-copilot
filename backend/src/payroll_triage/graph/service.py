"""Triage service: runs the graph per case, pauses at the two human checkpoints, resumes with
the human's input (ADR-018).

Interrupt 1 (`decide`): the action and the actor. Interrupt 2 (`confirm_message`), for return
and escalate only: the confirmed message from the same actor, or a cancel from any actor.
Every resume value is validated before `Command(resume=...)`, because a resume value is
persisted with the thread even when the node then fails. A stalled thread is resumed only with
the input already stored in it.
"""

from __future__ import annotations

import datetime as dt
import threading
from typing import Any

from langgraph.types import Command

from payroll_triage.db.store import CaseStore, case_id_for
from payroll_triage.graph.execute import (
    MESSAGE_ACTIONS,
    RECIPIENTS,
    DecisionError,
    validate_choice,
    validate_message,
)
from payroll_triage.graph.nodes import Deps, draft_is_valid

# LangGraph's channel for pending resume values (private constant `langgraph.constants.RESUME`).
_RESUME_CHANNEL = "__resume__"
_DRAFTING = (["draft"], ["validate_draft"])
_EXECUTING = (["execute"], ["audit"])


class CaseNotFound(KeyError):
    pass


class CaseNotWaiting(RuntimeError):
    pass


class TriageService:
    def __init__(self, graph, deps: Deps) -> None:
        self.graph = graph
        self.deps = deps
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    @property
    def store(self) -> CaseStore:
        return self.deps.store

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    def _lock(self, thread_id: str) -> threading.Lock:
        """Resumes of one case are serialized in this process; across processes the guarded
        status update in `apply_execution` prevents a second execution (ADR-018)."""
        with self._locks_guard:
            return self._locks.setdefault(thread_id, threading.Lock())

    def run_timecard(self, timecard_id: str) -> dict[str, Any]:
        """Run detect to the human checkpoint (or to the end for a clean week)."""
        thread_id = case_id_for(timecard_id)
        with self._lock(thread_id):
            existing = self.store.get_case_by_timecard(timecard_id)
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

    def _pending_resume(self, thread_id: str) -> Any:
        """The resume value already accepted at a checkpoint node whose run then failed."""
        saved = self.graph.checkpointer.get_tuple(self._config(thread_id))
        for _task, channel, value in (saved.pending_writes or []) if saved else []:
            if channel == _RESUME_CHANNEL:
                return value
        return None

    def _resume(self, thread_id: str, node: str, value: dict[str, Any]) -> dict[str, Any]:
        pending = self._pending_resume(thread_id)
        if pending is not None:
            if pending != value:
                raise CaseNotWaiting(
                    f"the {node} already accepted {pending!r}; resubmit it to retry"
                )
            return self.graph.invoke(None, self._config(thread_id))
        return self.graph.invoke(Command(resume=value), self._config(thread_id))

    @staticmethod
    def _same(stored: dict[str, Any], submitted: dict[str, Any], keys: tuple[str, ...]) -> None:
        if any(stored.get(k) != submitted.get(k) for k in keys):
            raise CaseNotWaiting(
                f"the case already holds the decision of {stored.get('actor')!r} "
                f"({stored.get('action')!r}) pending completion; resubmit that decision to retry"
            )

    def decide(self, case_id: str, choice: dict[str, Any]) -> dict[str, Any]:
        """Interrupt 1. Approve executes; return and escalate stop at the message step with the
        draft written for the chosen action."""
        clean = validate_choice(choice)
        case, snapshot = self.waiting_state(case_id)
        thread_id = case.thread_id
        with self._lock(thread_id):
            case, snapshot = self.waiting_state(case_id)
            before = snapshot.config["configurable"].get("checkpoint_id")
            stored = (snapshot.values or {}).get("decision") or {}
            waiting = list(snapshot.next)
            retried = True
            if waiting == ["human_checkpoint"]:
                result = self._resume(thread_id, "human checkpoint", clean)
                retried = False
            elif waiting in _DRAFTING or (
                waiting in _EXECUTING and stored.get("action") not in MESSAGE_ACTIONS
            ):
                self._same(stored, clean, ("action", "actor"))
                result = self.graph.invoke(None, self._config(thread_id))
            elif waiting == ["message_checkpoint"]:
                raise CaseNotWaiting(
                    f"case {case_id} waits for the message of the {stored.get('action')} chosen by "
                    f"{stored.get('actor')!r}: confirm or cancel it (POST /cases/{{id}}/message)"
                )
            else:
                raise CaseNotWaiting(f"case {case_id} is not waiting at the human checkpoint")
        return self._outcome(case_id, result, before, retried)

    def confirm_message(self, case_id: str, reply: dict[str, Any]) -> dict[str, Any]:
        """Interrupt 2: the confirmed message (chooser only) or a cancel (any actor)."""
        case, _ = self.waiting_state(case_id)
        thread_id = case.thread_id
        with self._lock(thread_id):
            case, snapshot = self.waiting_state(case_id)
            before = snapshot.config["configurable"].get("checkpoint_id")
            stored = (snapshot.values or {}).get("decision") or {}
            waiting = list(snapshot.next)
            retried = True
            if waiting == ["message_checkpoint"]:
                clean = validate_message(reply, stored)
                result = self._resume(thread_id, "message step", clean)
                retried = False
            elif waiting in _EXECUTING and stored.get("action") in MESSAGE_ACTIONS:
                submitted = {
                    "action": stored.get("action"),
                    "actor": (reply.get("actor") or "").strip(),
                    "message": (reply.get("message") or "").strip(),
                    "recipient_role": reply.get("recipient_role")
                    or RECIPIENTS[stored["action"]][0],
                }
                self._same(stored, submitted, ("actor", "message", "recipient_role"))
                result = self.graph.invoke(None, self._config(thread_id))
            elif waiting == ["human_checkpoint"]:
                raise CaseNotWaiting(
                    f"case {case_id} waits for the action to be chosen (POST /cases/{{id}}/decide)"
                )
            else:
                raise CaseNotWaiting(f"case {case_id} is not waiting for a message")
        return self._outcome(case_id, result, before, retried)

    def _outcome(
        self, case_id: str, result: dict[str, Any], before: str | None, retried: bool
    ) -> dict[str, Any]:
        case, after = self.waiting_state(case_id)
        values = after.values or {}
        waiting = list(after.next)
        out = {
            "case_id": case_id,
            "status": case.status,
            "waiting_on": waiting,
            "execution": result.get("execution"),
            "audit_ids": result.get("audit_ids", []),
            "llm_calls": result.get("llm_calls", []),
            "checkpoint_id_before": before,
            "checkpoint_id_after": after.config["configurable"].get("checkpoint_id"),
            "retried_execution": retried,
        }
        if waiting == ["message_checkpoint"]:
            out["chosen_action"] = (values.get("decision") or {}).get("action")
            out["draft"] = values.get("draft") if draft_is_valid(values) else None
            out["draft_status"] = self._output_status(case_id, values)["draft"]
            out["review_reason"] = case.review_reason
        return out

    def _output_status(self, case_id: str, values: dict[str, Any]) -> dict[str, str]:
        """Per output of the current round: valid, invalid, not_validated (validation never
        reached) or missing (no output in this round). Read from the suggestion ids held in the
        thread, never from the latest row of a kind (a cancelled round's draft is not current)."""
        by_id = {s["id"]: s["validation_status"] for s in self.store.list_suggestions(case_id)}
        ids = values.get("suggestion_ids") or {}
        return {
            kind: by_id.get(ids[kind], "missing") if kind in ids else "missing"
            for kind in ("explain", "propose", "draft")
        }

    def case_detail(self, case_id: str) -> dict[str, Any]:
        case, snapshot = self.waiting_state(case_id)
        tc = self.store.get_timecard(case.timecard_id)
        values = snapshot.values or {}
        waiting = list(snapshot.next)
        output_status = self._output_status(case_id, values)
        decision = values.get("decision") or {}
        sent = set(values.get("passage_keys", []))
        return {
            "case": case.to_dict(),
            "timecard": tc.to_dict() if tc else None,
            "explanation": values.get("explanation"),
            "proposal": values.get("proposal"),
            # Shown only when it validated (ADR-018): a failed or invalid draft is not shown.
            "draft": values.get("draft") if output_status["draft"] == "valid" else None,
            # A non-valid output must never be shown as validated.
            "output_status": output_status,
            "validation": values.get("validation"),
            "draft_validation": values.get("draft_validation"),
            "review_reason": values.get("review_reason") or case.review_reason,
            "chunks": [
                {
                    **{k: c[k] for k in ("citation_key", "source_type", "version", "heading")},
                    "sent_to_model": c["citation_key"] in sent,
                }
                for c in values.get("chunks", [])
            ],
            "chosen_action": decision.get("action"),
            "decision": values.get("decision"),
            "execution": values.get("execution"),
            "cancelled_rounds": values.get("cancelled_rounds", 0),
            "llm_calls": values.get("llm_calls", []),
            "pending_retry": waiting in _EXECUTING or waiting in _DRAFTING,
            "checkpoint_id": snapshot.config["configurable"].get("checkpoint_id"),
            "waiting_on": waiting,
            "suggestions": self.store.list_suggestions(case_id),
        }


__all__ = ["CaseNotFound", "CaseNotWaiting", "DecisionError", "TriageService"]
