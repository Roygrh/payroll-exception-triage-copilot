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

from payroll_triage.calc import clock_time
from payroll_triage.data.scenarios import load_catalog
from payroll_triage.engine.facts import fact_units
from payroll_triage.graph.execute import MAX_MESSAGE_LENGTH, RECIPIENTS, DecisionError
from payroll_triage.graph.service import CaseNotFound, CaseNotWaiting, TriageService
from payroll_triage.runtime import Runtime, build_runtime
from payroll_triage.timecards import TIME_FIELDS, Timecard


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


def _rule_titles(service: TriageService, findings: list[dict[str, Any]]) -> dict[str, str]:
    rules = service.deps.params.rules
    return {f["rule_id"]: rules[f["rule_id"]].title for f in findings if f["rule_id"] in rules}


def _occupation_title(service: TriageService, deal_memo_id: str) -> str | None:
    memo = service.store.get_deal_memo(deal_memo_id)
    return memo.occupation_title if memo else None


def _clock_or_none(hours: float | None) -> str | None:
    return None if hours is None else clock_time(hours)


def _finding_days(tc: Timecard | None, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The timecard events of each finding's day as HH:MM times of day (`calc.clock_time`), as
    the prompts show them (P1.I2b.S8); the UI never formats decimal hours itself."""
    days = {d.date.isoformat(): d for d in tc.days} if tc else {}
    out = []
    for f in findings:
        day = days.get(f.get("day_date") or "")
        if day is None:
            continue
        out.append(
            {
                "rule_id": f["rule_id"],
                "day_date": f["day_date"],
                "weekday": day.weekday,
                "events": [
                    {"field": name, "time": _clock_or_none(getattr(day, name))}
                    for name in TIME_FIELDS
                ],
            }
        )
    return out


@app.get("/health")
def health() -> dict[str, Any]:
    runtime: Runtime = app.state.runtime
    return {"status": "ok", "settings": runtime.settings.redacted()}


@app.get("/context")
def context() -> dict[str, Any]:
    """Read-only header context for the approver UI (Iteration 4): the demo week, the next
    payroll run, the agreement in force, the demo approver, the allowed message recipients and
    the message length limit."""
    service = _service()
    catalog = load_catalog()
    agreement = service.deps.params.agreement
    return {
        "week_ending": catalog.demo_week_ending.isoformat(),
        "as_of_date": service.deps.clock.as_of.isoformat(),
        "payroll_run_date": service.deps.clock.payroll_run_date.isoformat(),
        "agreement": {"code": agreement.code, "name": agreement.name, "version": agreement.version},
        "demo_approver": catalog.demo_approver,
        "recipients": {action: list(roles) for action, roles in RECIPIENTS.items()},
        "max_message_length": MAX_MESSAGE_LENGTH,
    }


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
                # Added in Iteration 4 (optional, read-only).
                "employee_id": tc.employee_id if tc else None,
                "occupation_code": tc.occupation_code if tc else None,
                "occupation_title": _occupation_title(service, case.deal_memo_id),
                "rule_titles": _rule_titles(service, case.findings),
            }
        )
    return {"count": len(cases), "cases": cases}


@app.get("/cases/{case_id}")
def case_detail(case_id: str) -> dict[str, Any]:
    service = _service()
    try:
        detail = service.case_detail(case_id)
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found") from exc
    findings = detail["case"]["findings"]
    tc = service.store.get_timecard(detail["case"]["timecard_id"])
    # Added in Iteration 4 (optional, read-only): display data the approver UI needs.
    detail["finding_days"] = _finding_days(tc, findings)
    detail["fact_units"] = {f["rule_id"]: fact_units(f["rule_id"]) for f in findings}
    detail["rule_titles"] = _rule_titles(service, findings)
    detail["occupation_title"] = _occupation_title(service, detail["case"]["deal_memo_id"])
    return detail


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
