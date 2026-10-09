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
from tests.support.fake_adapter import FakeAdapter, good_outputs
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
            k: (lambda r, k=k: good_outputs("CGMA-2026.1-8.2", _memo(r), _action(r))[k])
            for k in ("explain", "propose", "draft")
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
    assert [e["entry_kind"] for e in audit["entries"]] == ["suggestion"] * 3 + ["validation"]

    # step 3: edit the draft and return
    edited = detail["draft"]["body"] + " Edited by the approver."
    bad = client.post(f"/cases/{top['id']}/decide", json={"action": "return", "actor": "sam"})
    assert bad.status_code == 422
    decided = client.post(
        f"/cases/{top['id']}/decide",
        json={"action": "return", "actor": "sam.verhoeven", "message": edited},
    )
    assert decided.status_code == 200, decided.text
    decided = decided.json()
    assert decided["status"] == "returned"
    assert decided["checkpoint_id_before"] != decided["checkpoint_id_after"]
    audit = client.get(f"/cases/{top['id']}/audit").json()["entries"]
    assert [e["entry_kind"] for e in audit][-2:] == ["decision", "execution"]
    assert audit[-2]["payload"]["message"] == edited and audit[-2]["actor"] == "sam.verhoeven"
    assert (
        client.post(
            f"/cases/{top['id']}/decide", json={"action": "approve", "actor": "sam.verhoeven"}
        ).status_code
        == 409
    )
    assert client.get("/queue").json()["count"] == 1
    assert client.get("/cases/CASE-NOPE").status_code == 404
