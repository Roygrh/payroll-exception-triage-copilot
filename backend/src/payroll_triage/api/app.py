"""REST API for the exception queue. The human identity comes from the request body (`actor`)
in Phase 1; there is no authentication yet. Every write goes through the graph's execute node
after the human checkpoint; the API itself only reads and resumes."""

from __future__ import annotations

import datetime as dt
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from payroll_triage.graph.execute import DecisionError
from payroll_triage.graph.service import CaseNotFound, CaseNotWaiting, TriageService
from payroll_triage.runtime import Runtime, build_runtime


class DecisionBody(BaseModel):
    action: Literal["approve", "return", "escalate"]
    actor: str = Field(min_length=1, max_length=200)
    message: str | None = Field(default=None, max_length=4000)
    recipient_role: Literal["employee", "department_head"] = "employee"


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


app = FastAPI(title="Payroll Exception Triage Copilot API", version="0.2.0", lifespan=lifespan)


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


@app.post("/cases/{case_id}/decide")
def decide(case_id: str, body: DecisionBody) -> dict[str, Any]:
    try:
        return _service().decide(case_id, body.model_dump())
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found") from exc
    except CaseNotWaiting as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DecisionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
