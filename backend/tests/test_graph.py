"""Graph behavior with the fake adapter and in-memory store: checkpoint, resume, review paths."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from payroll_triage.corpus.render import render_agreement
from payroll_triage.data.generator import load_generated_timecards
from payroll_triage.db.seed import all_deal_memos
from payroll_triage.graph.build import NODE_NAMES, build_graph
from payroll_triage.graph.execute import DecisionError, plan_execution
from payroll_triage.graph.nodes import Deps, numbers_in, stray_numbers
from payroll_triage.graph.service import CaseNotWaiting, TriageService
from payroll_triage.params import load_parameters
from payroll_triage.retrieval.chunker import build_corpus
from payroll_triage.runtime import demo_clock
from tests.support.fake_adapter import (
    FakeAdapter,
    good_draft,
    good_outputs,
    with_explanation,
    with_proposal,
)
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


def make_service(timecards, memos, corpus, params, adapter):
    store = MemoryStore(timecards, memos)
    deps = Deps(
        store=store,
        retriever=MemoryRetriever(corpus),
        adapter=adapter,
        params=params,
        clock=demo_clock(),
    )
    graph = build_graph(deps, InMemorySaver())
    return TriageService(graph, deps), store


def test_graph_nodes_match_the_architecture_document():
    doc = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "docs"
        / "architecture"
        / "overview.md"
    ).read_text(encoding="utf-8")
    for name in NODE_NAMES:
        assert name in doc, name


def test_happy_path_pauses_at_checkpoint_with_validated_citations(timecards, memos, corpus, params):
    tc = _tc(timecards, "SC-03")
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-01", "approve"))
    service, store = make_service(timecards, memos, corpus, params, adapter)
    result = service.run_timecard(tc.id)
    assert result["status"] == "awaiting_decision"
    assert result["waiting_on"] == ["human_checkpoint"] and result["checkpoint_id"]
    # one merged call before the human decides; no draft before the decision (ADR-018)
    assert [c["node"] for c in result["llm_calls"]] == ["explain_propose"]
    case = store.get_case(result["case_id"])
    assert case.status == "awaiting_decision" and case.policy_action == "approve"
    detail = service.case_detail(case.id)
    assert detail["validation"]["valid"] and detail["proposal"]["proposed_action"] == "approve"
    assert {c["citation_key"] for c in detail["chunks"]} >= {
        SECTION_KEY,
        "DM-01",
        "CGMA-2026.1-SCH-B",
    }
    kinds = [s["kind"] for s in store.list_suggestions(case.id)]
    assert kinds == ["explain", "propose"]
    assert all(s["validation_status"] == "valid" for s in store.list_suggestions(case.id))
    audit = store.list_audit(case.id)
    assert [a["entry_kind"] for a in audit] == ["suggestion", "validation"]
    assert audit[0]["actor"] == "llm:fake/fake-model"
    assert audit[0]["payload"]["kinds"] == ["explain", "propose"]
    # only the finding's own sections and the deal memo are sent; the rest is recorded
    sent = {c["citation_key"] for c in detail["chunks"] if c["sent_to_model"]}
    assert sent == {SECTION_KEY, "CGMA-2026.1-8.3", "CGMA-2026.1-SCH-B", "DM-01"}
    prompt = adapter.requests[0].messages[0].content
    unsent = [c["citation_key"] for c in detail["chunks"] if not c["sent_to_model"]]
    assert unsent and all(f"[{k}]" not in prompt for k in unsent)
    # the prompts never ask the model to compute and show the facts by name
    for req in adapter.requests:
        text = req.messages[0].content.lower()
        assert "calculate" not in text.replace("never calculate", "")
        assert '"hours_to_meal"' in text and '"penalty_usd"' in text
    assert store.premium_lines == [] and store.decisions == []  # nothing executed before the human
    assert detail["output_status"] == {"explain": "valid", "propose": "valid", "draft": "missing"}
    assert detail["draft"] is None


def test_resume_with_edited_message_executes_return_under_human_identity(
    timecards, memos, corpus, params
):
    tc = _tc(timecards, "SC-05")
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-02", "return"))
    service, store = make_service(timecards, memos, corpus, params, adapter)
    case_id = service.run_timecard(tc.id)["case_id"]
    assert service.case_detail(case_id)["draft"] is None  # nothing drafted before the decision
    chosen = service.decide(case_id, {"action": "return", "actor": "sam.verhoeven"})
    assert chosen["waiting_on"] == ["message_checkpoint"] and chosen["draft_status"] == "valid"
    assert chosen["status"] == "awaiting_decision" and store.decisions == []
    original = chosen["draft"]["body"]
    assert chosen["draft"]["for_action"] == "return"
    edited = original + " Please confirm the meal times by Monday."
    outcome = service.confirm_message(case_id, {"actor": "sam.verhoeven", "message": edited})
    assert outcome["status"] == "returned"
    assert outcome["checkpoint_id_before"] != outcome["checkpoint_id_after"]
    assert store.timecards[tc.id].status == "Rejected"
    assert store.return_messages[-1]["body"] == edited
    assert store.return_messages[-1]["sent_by"] == "sam.verhoeven"
    assert store.decisions[-1]["actor"] == "sam.verhoeven"
    audit = store.list_audit(case_id)
    assert [a["entry_kind"] for a in audit] == [
        "suggestion",
        "validation",
        "decision",
        "suggestion",
        "decision",
        "execution",
    ]
    assert audit[2]["payload"]["stage"] == "action_chosen"
    decision_entry = audit[4]
    assert decision_entry["actor"] == "sam.verhoeven"
    assert decision_entry["payload"]["stage"] == "executed"
    assert decision_entry["payload"]["original_draft"] == original
    assert decision_entry["payload"]["message"] == edited
    assert decision_entry["payload"]["message_edited"] is True
    assert decision_entry["payload"]["message_source"] == "draft_edited"
    assert decision_entry["payload"]["case_status_before"] == "awaiting_decision"  # S5
    execution_entry = next(a for a in audit if a["entry_kind"] == "execution")
    assert execution_entry["payload"]["timecard_status"] == "Rejected"
    assert execution_entry["actor"] == "sam.verhoeven"
    with pytest.raises(CaseNotWaiting):
        service.decide(case_id, {"action": "approve", "actor": "x"})
    assert service.store.list_queue() == []


def test_approve_adds_premium_lines_from_engine_facts(timecards, memos, corpus, params):
    tc = _tc(timecards, "SC-03")
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-01", "approve"))
    service, store = make_service(timecards, memos, corpus, params, adapter)
    case_id = service.run_timecard(tc.id)["case_id"]
    outcome = service.decide(case_id, {"action": "approve", "actor": "sam.verhoeven"})
    assert outcome["status"] == "approved"
    assert adapter.kinds() == ["explain_propose"]  # approve makes no draft call (ADR-018)
    assert store.timecards[tc.id].status == "Ready for approver 2"
    assert len(store.premium_lines) == 1
    assert store.premium_lines[0]["amount_usd"] == params.meal.penalty_schedule_usd[0]
    assert store.premium_lines[0]["created_by"] == "sam.verhoeven"
    assert outcome["execution"]["premium_total_usd"] == f"{params.meal.penalty_schedule_usd[0]:.2f}"


def test_llm_failure_routes_to_needs_human_review_with_no_generated_text(
    timecards, memos, corpus, params
):
    tc = _tc(timecards, "SC-03")
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-01", "approve"), fail={"explain_propose"})
    service, store = make_service(timecards, memos, corpus, params, adapter)
    result = service.run_timecard(tc.id)
    assert result["status"] == "needs_human_review"
    assert "explain_propose: LLM call failed" in result["review_reason"]
    assert result["waiting_on"] == ["human_checkpoint"]
    detail = service.case_detail(result["case_id"])
    assert detail["explanation"] is None and detail["proposal"] is None
    assert detail["draft"] is None
    assert detail["output_status"] == {
        "explain": "missing",
        "propose": "missing",
        "draft": "missing",
    }
    assert store.list_suggestions(result["case_id"]) == []
    review = next(a for a in store.list_audit(result["case_id"]) if a["entry_kind"] == "review")
    assert review["payload"]["facts_only"] is True and review["actor"] == "system"
    # the approver can still decide; the note is drafted for the escalation, then the human's
    # own text is what gets sent
    chosen = service.decide(result["case_id"], {"action": "escalate", "actor": "sam.verhoeven"})
    assert chosen["waiting_on"] == ["message_checkpoint"]
    assert chosen["draft"]["recipient_role"] == "payroll_specialist"
    outcome = service.confirm_message(
        result["case_id"], {"actor": "sam.verhoeven", "message": "Specialist, please check."}
    )
    assert (
        outcome["status"] == "escalated"
        and store.escalations[-1]["note"] == "Specialist, please check."
    )
    assert store.timecards[tc.id].status == "Ready for approver 1"  # escalate leaves it untouched
    assert outcome["execution"]["message_source"] == "draft_edited"
    assert outcome["execution"]["decision_id"] == store.decisions[-1]["id"]
    decisions = [a for a in store.list_audit(result["case_id"]) if a["entry_kind"] == "decision"]
    assert decisions[-1]["payload"]["case_status_before"] == "needs_human_review"  # S5


def test_invalid_citation_routes_to_review(timecards, memos, corpus, params):
    tc = _tc(timecards, "SC-03")
    outputs = with_explanation(
        good_outputs(SECTION_KEY, "DM-01", "approve"),
        explanation="Per the agreement [CGMA-2026.1-99.9] the meal was late.",
        citation_keys=["CGMA-2026.1-99.9"],
    )
    service, store = make_service(timecards, memos, corpus, params, FakeAdapter(outputs))
    result = service.run_timecard(tc.id)
    assert result["status"] == "needs_human_review"
    assert "CGMA-2026.1-99.9 unknown_key" in result["review_reason"]
    assert "required missing" in result["review_reason"]
    statuses = {
        s["kind"]: s["validation_status"] for s in store.list_suggestions(result["case_id"])
    }
    assert statuses == {"explain": "invalid", "propose": "valid"}


def test_stray_number_routes_to_review(timecards, memos, corpus, params):
    tc = _tc(timecards, "SC-03")
    outputs = with_explanation(
        good_outputs(SECTION_KEY, "DM-01", "approve"),
        explanation=f"The meal began 0.75 hours late [{SECTION_KEY}].",
    )
    service, _ = make_service(timecards, memos, corpus, params, FakeAdapter(outputs))
    result = service.run_timecard(tc.id)
    assert result["status"] == "needs_human_review"
    assert "numbers not in the facts" in result["review_reason"]


def test_proposal_mismatch_routes_to_review_without_overwrite(timecards, memos, corpus, params):
    tc = _tc(timecards, "SC-03")
    outputs = with_proposal(good_outputs(SECTION_KEY, "DM-01", "approve"), proposed_action="return")
    service, store = make_service(timecards, memos, corpus, params, FakeAdapter(outputs))
    result = service.run_timecard(tc.id)
    assert result["status"] == "needs_human_review"
    assert "differs from the policy action 'approve'" in result["review_reason"]
    detail = service.case_detail(result["case_id"])
    assert detail["proposal"]["proposed_action"] == "return"  # shown, not overwritten
    assert store.get_case(result["case_id"]).policy_action == "approve"


def test_clean_week_creates_no_case_and_rerun_is_idempotent(timecards, memos, corpus, params):
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-01", "approve"))
    service, store = make_service(timecards, memos, corpus, params, adapter)
    clean = _tc(timecards, "SC-01")
    assert service.run_timecard(clean.id) == {
        "case_id": None,
        "status": "clean",
        "timecard_id": clean.id,
    }
    assert store.cases == {}
    tc = _tc(timecards, "SC-03")
    first = service.run_timecard(tc.id)
    again = service.run_timecard(tc.id)
    assert again == {
        "case_id": first["case_id"],
        "status": "awaiting_decision",
        "already_existed": True,
    }
    assert len(adapter.requests) == 1


def test_ingest_demo_week_fills_queue_in_priority_order(timecards, memos, corpus, params):
    adapter = FakeAdapter(
        {
            "explain_propose": lambda r: good_outputs(SECTION_KEY, _memo_for(r), _action_for(r))[
                "explain_propose"
            ],
            "draft": good_draft(SECTION_KEY),
        }
    )
    service, store = make_service(timecards, memos, corpus, params, adapter)
    results = service.ingest_week(demo_clock().as_of.__class__(2026, 3, 14))
    cases = [r for r in results if r["case_id"]]
    assert {r["timecard_id"] for r in results} == {
        t.id for t in timecards.values() if t.week_ending.isoformat() == "2026-03-14"
    }
    assert len(cases) == 2  # SC-03 and SC-05: only MEAL_PERIOD is wired in Iteration 2
    queue = store.list_queue()
    assert [c.policy_action for c in queue] == ["return", "approve"]
    assert queue[0].priority_score > queue[1].priority_score


def _memo_for(request) -> str:
    return "DM-02" if "1002" in request.metadata["case_id"] else "DM-01"


def _action_for(request) -> str:
    return "return" if "1002" in request.metadata["case_id"] else "approve"


def test_numbers_extraction_and_decision_validation():
    assert numbers_in("6.5 hours, 8.25 USD, section 8.2, on 2026-03-10") == {
        __import__("decimal").Decimal(x) for x in ("6.5", "8.25", "8.2", "2026", "3", "10")
    }
    assert numbers_in("DM-01, EMP-1001, TC-EMP-1001-20260314 and CGMA-2026.1-8.2") == set()
    assert numbers_in("[CGMA-2026.1-SCH-B] lists 8.25") == {__import__("decimal").Decimal("8.25")}
    state = {"findings": [{"facts": {"hours_to_meal": 6.5}}], "case": {}, "chunks": []}
    assert stray_numbers("6.5 hours and 6 hours", state) == ["6"]
    with pytest.raises(DecisionError, match="message"):
        plan_execution("c", "t", [], {"action": "return", "actor": "a"})
    with pytest.raises(DecisionError, match="message"):
        plan_execution("c", "t", [], {"action": "escalate", "actor": "a"})  # no default note
    with pytest.raises(DecisionError, match="actor"):
        plan_execution("c", "t", [], {"action": "approve", "actor": " "})
    with pytest.raises(DecisionError, match="action"):
        plan_execution("c", "t", [], {"action": "skip", "actor": "a"})
    plan = plan_execution(
        "c",
        "t",
        [{"rule_id": "MEAL_PERIOD", "section": "8.2", "amount_usd": "0.00", "day_date": None}],
        {"action": "approve", "actor": "a"},
    )
    assert plan.premium_lines == () and plan.case_status_after == "approved"
