"""API surface with the in-memory runtime (no database, fake adapter)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from payroll_triage.api import app as api
from payroll_triage.config import get_settings
from payroll_triage.corpus.render import render_agreement
from payroll_triage.data.generator import load_generated_timecards
from payroll_triage.db.seed import all_deal_memos
from payroll_triage.graph.build import build_graph
from payroll_triage.graph.nodes import Deps
from payroll_triage.graph.service import TriageService
from payroll_triage.params import load_parameters
from payroll_triage.retrieval.chunker import build_corpus
from payroll_triage.runtime import Runtime, demo_clock
from tests.support.fake_adapter import FakeAdapter, good_draft, good_outputs
from tests.support.memory import MemoryRetriever, MemoryStore


class _NoPool:
    def close(self) -> None:
        pass


@pytest.fixture
def client(monkeypatch):
    params = load_parameters()
    memos = all_deal_memos()
    timecards = {t.id: t for t in load_generated_timecards()}
    adapter = FakeAdapter(
        {
            "explain_propose": lambda r: good_outputs("CGMA-2026.1-8.2", _memo(r), _action(r))[
                "explain_propose"
            ],
            "draft": good_draft("CGMA-2026.1-8.2"),
        }
    )
    deps = Deps(
        store=MemoryStore(timecards, memos),
        retriever=MemoryRetriever(build_corpus(params, memos, render_agreement(params))),
        adapter=adapter,
        params=params,
        clock=demo_clock(),
    )
    service = TriageService(build_graph(deps, InMemorySaver()), deps)
    runtime = Runtime(get_settings(), _NoPool(), _NoPool(), service)  # type: ignore[arg-type]
    monkeypatch.setattr(api, "build_runtime", lambda: runtime)
    with TestClient(api.app) as client:
        yield client


def _memo(request) -> str:
    return "DM-02" if "1002" in request.metadata["case_id"] else "DM-01"


def _action(request) -> str:
    return "return" if "1002" in request.metadata["case_id"] else "approve"


def test_demo_steps_one_to_three_over_the_api(client):
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["settings"]["llm_api_key"] in ("set", "missing")

    # step 1: ingest the demo week; clean weeks and filler produce no case
    ingest = client.post("/ingest", json={"week_ending": "2026-03-14"}).json()
    assert len(ingest["results"]) == 10
    queue = client.get("/queue").json()
    assert queue["count"] == 2
    assert [c["policy_action"] for c in queue["cases"]] == ["return", "approve"]
    assert all(c["rule_ids"] == ["MEAL_PERIOD"] for c in queue["cases"])
    top = queue["cases"][0]

    # step 2: open the top case, follow a citation
    detail = client.get(f"/cases/{top['id']}").json()
    assert detail["explanation"]["citation_keys"][0] == "CGMA-2026.1-8.2"
    assert detail["proposal"]["proposed_action"] == "return"
    assert detail["validation"]["valid"] and detail["waiting_on"] == ["human_checkpoint"]
    passage = client.get("/passages/CGMA-2026.1-8.2").json()
    assert passage["section"] == "8.2" and passage["version"] == "2026.1"
    assert client.get("/passages/CGMA-2026.1-99.9").status_code == 404
    audit = client.get(f"/cases/{top['id']}/audit").json()
    assert [e["entry_kind"] for e in audit["entries"]] == ["suggestion", "validation"]
    assert detail["draft"] is None and detail["output_status"]["draft"] == "missing"

    # step 3: choose Return, review the drafted message, edit, confirm (ADR-018)
    with_message = client.post(
        f"/cases/{top['id']}/decide",
        json={"action": "return", "actor": "sam.verhoeven", "message": "too early"},
    )
    assert with_message.status_code == 422  # the message is confirmed at /message
    early = client.post(
        f"/cases/{top['id']}/message", json={"actor": "sam.verhoeven", "message": "x"}
    )
    assert early.status_code == 409  # no action chosen yet
    chosen = client.post(
        f"/cases/{top['id']}/decide", json={"action": "return", "actor": "sam.verhoeven"}
    )
    assert chosen.status_code == 200, chosen.text
    chosen = chosen.json()
    assert chosen["waiting_on"] == ["message_checkpoint"] and chosen["draft_status"] == "valid"
    assert client.get(f"/cases/{top['id']}").json()["chosen_action"] == "return"
    again = client.post(
        f"/cases/{top['id']}/decide", json={"action": "approve", "actor": "sam.verhoeven"}
    )
    assert again.status_code == 409  # waiting for the message, not for an action
    edited = chosen["draft"]["body"] + " Edited by the approver."
    other = client.post(f"/cases/{top['id']}/message", json={"actor": "kim", "message": edited})
    assert other.status_code == 422  # only the actor who chose the action confirms
    empty = client.post(f"/cases/{top['id']}/message", json={"actor": "sam.verhoeven"})
    assert empty.status_code == 422
    decided = client.post(
        f"/cases/{top['id']}/message", json={"actor": "sam.verhoeven", "message": edited}
    )
    assert decided.status_code == 200, decided.text
    decided = decided.json()
    assert decided["status"] == "returned"
    assert decided["checkpoint_id_before"] != decided["checkpoint_id_after"]
    audit = client.get(f"/cases/{top['id']}/audit").json()["entries"]
    assert [e["entry_kind"] for e in audit][-2:] == ["decision", "execution"]
    assert audit[-2]["payload"]["message"] == edited and audit[-2]["actor"] == "sam.verhoeven"
    assert audit[-2]["payload"]["stage"] == "executed"
    assert (
        client.post(
            f"/cases/{top['id']}/decide", json={"action": "approve", "actor": "sam.verhoeven"}
        ).status_code
        == 409
    )
    assert client.get("/queue").json()["count"] == 1
    assert client.get("/cases/CASE-NOPE").status_code == 404
