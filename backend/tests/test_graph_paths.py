"""Additional graph paths from the Iteration 2 code review: empty retrieval, review-path approve,
uncited-passage numbers, resume of a case stuck in detected, holiday-aware urgency, catalog labels,
and the showcase refusing to compose a human message."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from payroll_triage import calc
from payroll_triage.corpus.render import render_agreement
from payroll_triage.data.generator import load_generated_timecards
from payroll_triage.data.scenarios import load_catalog
from payroll_triage.db.seed import all_deal_memos
from payroll_triage.engine.priority import PriorityInputs, is_urgent, priority_score
from payroll_triage.graph.build import build_graph
from payroll_triage.graph.execute import DEFAULT_INTAKE_STATUS, TIMECARD_STATUS_AFTER
from payroll_triage.graph.nodes import Deps, stray_numbers
from payroll_triage.graph.service import CaseNotWaiting, TriageService
from payroll_triage.params import load_parameters
from payroll_triage.retrieval.chunker import build_corpus
from payroll_triage.runtime import demo_clock
from payroll_triage.showcase import run_showcase
from tests.support.fake_adapter import FakeAdapter, good_outputs
from tests.support.memory import MemoryRetriever, MemoryStore

SECTION_KEY = "CGMA-2026.1-8.2"


@pytest.fixture(scope="module")
def params():
    return load_parameters()


@pytest.fixture(scope="module")
def memos():
    return all_deal_memos()


@pytest.fixture(scope="module")
def corpus(params, memos):
    return build_corpus(params, memos, render_agreement(params))


@pytest.fixture
def timecards():
    return {t.id: t for t in load_generated_timecards()}


def _tc(timecards, scenario_id):
    return next(t for t in timecards.values() if t.scenario_id == scenario_id)


def _service(timecards, memos, params, adapter, retriever):
    store = MemoryStore(timecards, memos)
    deps = Deps(
        store=store, retriever=retriever, adapter=adapter, params=params, clock=demo_clock()
    )
    return TriageService(build_graph(deps, InMemorySaver()), deps), store


def test_empty_retrieval_routes_to_review_without_llm_calls(timecards, memos, params):
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-01", "approve"))
    service, store = _service(timecards, memos, params, adapter, MemoryRetriever([]))
    result = service.run_timecard(_tc(timecards, "SC-03").id)
    assert result["status"] == "needs_human_review"
    assert result["review_reason"] == "retrieval returned no passages"
    assert adapter.requests == [] and store.list_suggestions(result["case_id"]) == []


def test_review_path_approve_adds_premium_under_human_identity(timecards, memos, corpus, params):
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-01", "approve"), fail={"explain"})
    service, store = _service(timecards, memos, params, adapter, MemoryRetriever(corpus))
    tc = _tc(timecards, "SC-03")
    case_id = service.run_timecard(tc.id)["case_id"]
    outcome = service.decide(case_id, {"action": "approve", "actor": "sam.verhoeven"})
    assert outcome["status"] == "approved" and outcome["retried_execution"] is False
    assert store.premium_lines[0]["amount_usd"] == params.meal.penalty_schedule_usd[0]
    assert store.timecards[tc.id].status == TIMECARD_STATUS_AFTER["approve"]


def test_number_only_in_an_uncited_passage_is_stray(timecards, memos, corpus, params):
    state = {
        "findings": [{"facts": {"hours_to_meal": 6.5}, "citation_keys": [SECTION_KEY]}],
        "case": {},
        "chunks": [
            {"citation_key": SECTION_KEY, "heading": "8.2", "body": "within 6.0 hours"},
            {"citation_key": "CGMA-2026.1-6.2", "heading": "6.2", "body": "above 12.0 hours"},
        ],
    }
    assert stray_numbers("12.0 hours", state, cited=[SECTION_KEY]) == ["12.0"]
    assert stray_numbers("12.0 hours", state, cited=[SECTION_KEY, "CGMA-2026.1-6.2"]) == []
    assert stray_numbers("6.0 and 6.5 and 8.2", state) == []
    assert stray_numbers("schema version 1", state) == ["1"]  # metadata is not a fact


class _ExplodingRetriever:
    def __init__(self, inner, explode_once=True):
        self.inner = inner
        self.calls = 0

    def get(self, key):
        return self.inner.get(key)

    def search(self, query, *, top_k=6):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("retriever down")
        return self.inner.search(query, top_k=top_k)


def test_case_stuck_in_detected_is_resumed_on_the_next_ingest(timecards, memos, corpus, params):
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-01", "approve"))
    retriever = _ExplodingRetriever(MemoryRetriever(corpus))
    service, store = _service(timecards, memos, params, adapter, retriever)
    tc = _tc(timecards, "SC-03")
    with pytest.raises(RuntimeError, match="retriever down"):
        service.run_timecard(tc.id)
    case = store.get_case_by_timecard(tc.id)
    assert case is not None and case.status == "detected"
    assert store.list_queue() == []  # not shown as open until it has a suggestion or a reason
    result = service.run_timecard(tc.id)
    assert result["status"] == "awaiting_decision" and result.get("already_existed") is None
    assert result["waiting_on"] == ["human_checkpoint"]
    assert store.decisions == [] and store.premium_lines == []
    assert len(adapter.requests) == 3
    outcome = service.decide(result["case_id"], {"action": "approve", "actor": "sam.verhoeven"})
    assert outcome["status"] == "approved" and store.decisions[-1]["actor"] == "sam.verhoeven"


class _FailingOnceStore(MemoryStore):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.failures = 0

    def apply_execution(self, plan):
        if self.failures == 0:
            self.failures += 1
            raise RuntimeError("database unavailable")
        return super().apply_execution(plan)


def test_execute_retry_runs_the_stored_decision_only(timecards, memos, corpus, params):
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-01", "approve"))
    store = _FailingOnceStore(timecards, memos)
    deps = Deps(
        store=store,
        retriever=MemoryRetriever(corpus),
        adapter=adapter,
        params=params,
        clock=demo_clock(),
    )
    service = TriageService(build_graph(deps, InMemorySaver()), deps)
    tc = _tc(timecards, "SC-03")
    case_id = service.run_timecard(tc.id)["case_id"]
    first = {"action": "approve", "actor": "approver.a"}
    with pytest.raises(RuntimeError, match="database unavailable"):
        service.decide(case_id, first)
    assert service.case_detail(case_id)["pending_retry"] is True
    assert service.case_detail(case_id)["waiting_on"] == ["execute"]
    with pytest.raises(CaseNotWaiting, match="already has a decision by 'approver.a'"):
        service.decide(case_id, {"action": "escalate", "actor": "approver.b"})
    outcome = service.decide(case_id, first)
    assert outcome["retried_execution"] is True and outcome["status"] == "approved"
    assert store.decisions == [
        {"id": 1, "case_id": case_id, "actor": "approver.a", "action": "approve", "message": None}
    ]
    assert store.escalations == []
    decision_entry = next(a for a in store.list_audit(case_id) if a["entry_kind"] == "decision")
    assert decision_entry["actor"] == "approver.a"


def test_urgency_honors_holidays(params):
    as_of = dt.date(2026, 3, 16)  # Monday
    window = params.queue.urgency_business_days
    run = calc.add_business_days(as_of, window + 1)  # one business day beyond the window
    holiday = calc.add_business_days(as_of, 1)  # the first business day after as_of
    assert not is_urgent(as_of, run, params)
    assert is_urgent(as_of, run, params, holidays=(holiday,))
    base = PriorityInputs(
        policy_action="approve",
        amount_usd=Decimal("0.00"),
        week_ending=as_of,
        as_of=as_of,
        payroll_run_date=run,
        holidays=(holiday,),
    )
    assert (
        priority_score(base, params) == params.queue.urgency_weight + params.queue.severity_weight
    )


def test_catalog_labels_match_the_code_defaults():
    catalog = load_catalog()
    assert catalog.queue_status == DEFAULT_INTAKE_STATUS
    assert catalog.labels["timecard_status_after"] == {
        k: v for k, v in TIMECARD_STATUS_AFTER.items() if v is not None
    }
    assert catalog.demo_approver
    clock = demo_clock()
    assert clock.intake_status == catalog.queue_status
    assert clock.timecard_status_after["escalate"] is None


def test_showcase_never_composes_the_human_message(timecards, memos, corpus, params, capsys):
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-02", "return"), fail={"draft"})
    service, store = _service(timecards, memos, params, adapter, MemoryRetriever(corpus))
    with pytest.raises(ValueError, match="needs --message"):
        run_showcase(service, "SC-05", "sam.verhoeven", "return", None)
    assert store.return_messages == [] and store.decisions == []
    capsys.readouterr()


def test_showcase_sends_the_validated_draft_verbatim(timecards, memos, corpus, params, capsys):
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-02", "return"))
    service, store = _service(timecards, memos, params, adapter, MemoryRetriever(corpus))
    summary = run_showcase(service, "SC-05", "sam.verhoeven", "return", None)
    assert summary["status_after"] == "returned"
    draft = store.list_suggestions(summary["case_id"])[2]["content"]["body"]
    assert store.return_messages[-1]["body"] == draft
    capsys.readouterr()
