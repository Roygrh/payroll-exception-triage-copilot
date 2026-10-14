"""REST API for the exception queue (ADR-018: decide, then confirm the message). The human
identity comes from the request body (`actor`) in Phase 1; there is no authentication yet.
Every write goes through the graph's execute node after the human checkpoints; the API itself
only reads and resumes."""

from __future__ import annotations

import datetime as dt
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from payroll_triage.graph.execute import MAX_MESSAGE_LENGTH, DecisionError
from payroll_triage.graph.service import CaseNotFound, CaseNotWaiting, TriageService
from payroll_triage.runtime import Runtime, build_runtime


class DecisionBody(BaseModel):
    """Interrupt 1: the action and the actor. The message comes after, at /message (ADR-018)."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "return", "escalate"]
    actor: str = Field(min_length=1, max_length=200)


class MessageBody(BaseModel):
    """Interrupt 2: the confirmed message (by the actor who chose the action) or a cancel."""

    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1, max_length=200)
    message: str | None = Field(default=None, max_length=MAX_MESSAGE_LENGTH)
    recipient_role: Literal["employee", "department_head", "payroll_specialist"] | None = None
    cancel: bool = False


class IngestBody(BaseModel):
    week_ending: dt.date


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = build_runtime()
    app.state.runtime = runtime
    try:
        yield
    finally:
        runtime.close()


app = FastAPI(title="Payroll Exception Triage Copilot API", version="0.3.0", lifespan=lifespan)


def _service() -> TriageService:
    runtime: Runtime = app.state.runtime
    return runtime.service


@app.get("/health")
def health() -> dict[str, Any]:
    runtime: Runtime = app.state.runtime
    return {"status": "ok", "settings": runtime.settings.redacted()}


@app.post("/ingest")
def ingest(body: IngestBody) -> dict[str, Any]:
    results = _service().ingest_week(body.week_ending)
    return {"week_ending": body.week_ending.isoformat(), "results": results}


@app.get("/queue")
def queue() -> dict[str, Any]:
    service = _service()
    cases = []
    for case in service.store.list_queue():
        tc = service.store.get_timecard(case.timecard_id)
        cases.append(
            {
                **case.to_dict(),
                "employee_name": tc.employee_name if tc else None,
                "department": tc.department if tc else None,
                "rule_ids": sorted({f["rule_id"] for f in case.findings}),
            }
        )
    return {"count": len(cases), "cases": cases}


@app.get("/cases/{case_id}")
def case_detail(case_id: str) -> dict[str, Any]:
    try:
        return _service().case_detail(case_id)
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found") from exc


def _resume(case_id: str, call) -> dict[str, Any]:
    try:
        return call()
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found") from exc
    except CaseNotWaiting as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DecisionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/cases/{case_id}/decide")
def decide(case_id: str, body: DecisionBody) -> dict[str, Any]:
    """Approve executes. Return and escalate draft the message for that action (one LLM call,
    seconds to tens of seconds on the free tier) and wait at the message step; repeating the
    same request after a client timeout resumes the same run."""
    return _resume(case_id, lambda: _service().decide(case_id, body.model_dump()))


@app.post("/cases/{case_id}/message")
def confirm_message(case_id: str, body: MessageBody) -> dict[str, Any]:
    payload = body.model_dump(exclude_none=True)
    if not body.cancel:
        payload.pop("cancel")
    return _resume(case_id, lambda: _service().confirm_message(case_id, payload))


@app.get("/cases/{case_id}/audit")
def audit(case_id: str) -> dict[str, Any]:
    service = _service()
    if service.store.get_case(case_id) is None:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found")
    return {"case_id": case_id, "entries": service.store.list_audit(case_id)}


@app.get("/passages/{citation_key}")
def passage(citation_key: str) -> dict[str, Any]:
    chunk = _service().deps.retriever.get(citation_key)
    if chunk is None:
        raise HTTPException(status_code=404, detail=f"no passage for {citation_key}")
    return chunk.to_dict()
