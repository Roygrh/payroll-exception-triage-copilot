"""Iteration 2b (ADR-018): hours_late as a fact, pseudo-references, the draft after the human
decision with its own checkpoint, token efficiency and the audit field fix."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from payroll_triage.corpus.render import render_agreement
from payroll_triage.data.generator import load_generated_timecards
from payroll_triage.db.seed import all_deal_memos
from payroll_triage.engine import detect
from payroll_triage.engine.facts import MealPeriodFacts
from payroll_triage.evals.manifest import build_manifest
from payroll_triage.graph import prompts
from payroll_triage.graph.build import build_graph
from payroll_triage.graph.execute import DecisionError
from payroll_triage.graph.nodes import (
    Deps,
    build_case,
    cited_keys,
    clock_times_with_unit,
    pseudo_references,
    stray_numbers,
    unit_mismatches,
    unit_numbers,
    unknown_clock_times,
)
from payroll_triage.graph.service import _RESUME_CHANNEL, CaseNotWaiting, TriageService
from payroll_triage.params import load_parameters
from payroll_triage.retrieval.chunker import build_corpus
from payroll_triage.runtime import demo_clock
from payroll_triage.showcase import dry_run, dry_run_requests
from payroll_triage.tokens import estimate_request
from tests.support.fake_adapter import (
    FakeAdapter,
    chosen_action,
    good_outputs,
    with_explanation,
    with_proposal,
)
from tests.support.memory import MemoryRetriever, MemoryStore

SECTION_KEY = "CGMA-2026.1-8.2"
ACTOR = "sam.verhoeven"


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


def _service(timecards, memos, corpus, params, adapter, store_cls=MemoryStore):
    store = store_cls(timecards, memos)
    deps = Deps(
        store=store,
        retriever=MemoryRetriever(corpus),
        adapter=adapter,
        params=params,
        clock=demo_clock(),
    )
    return TriageService(build_graph(deps, InMemorySaver()), deps), store


def _decisions(store, case_id):
    return [a for a in store.list_audit(case_id) if a["entry_kind"] == "decision"]


# ---------- S1: hours_late is an engine fact; the model never converts ----------


def test_hours_late_is_in_the_facts_and_the_manifest():
    assert "hours_late" in MealPeriodFacts.model_fields
    sc03 = next(c for c in build_manifest()["cases"] if c["scenario_id"] == "SC-03")
    facts = sc03["expected_findings"][0]["facts"]
    assert facts["minutes_late"] == 30 and facts["hours_late"] == 0.5


def test_hours_late_equals_minutes_late_for_every_meal_finding():
    findings = [
        f
        for case in build_manifest()["cases"]
        for f in case["expected_findings"]
        if f["rule_id"] == "MEAL_PERIOD"
    ]
    assert len(findings) >= 7
    for f in findings:
        assert f["facts"]["hours_late"] == round(f["facts"]["minutes_late"] / 60, 1)


def test_half_hour_is_stray_without_hours_late_and_valid_with_it():
    base = {"hours_to_meal": 6.5, "minutes_late": 30}
    text = f"The meal began 0.5 hours late [{SECTION_KEY}]."
    without = {"findings": [{"facts": base, "citation_keys": []}], "case": {}, "chunks": []}
    with_fact = {
        "findings": [{"facts": {**base, "hours_late": 0.5}, "citation_keys": []}],
        "case": {},
        "chunks": [],
    }
    assert stray_numbers(text, without) == ["0.5"]
    assert stray_numbers(text, with_fact) == []


def test_half_hour_in_the_explanation_validates_on_sc03(timecards, memos, corpus, params):
    outputs = with_explanation(
        good_outputs(SECTION_KEY, "DM-01", "approve"),
        explanation=f"The meal began 0.5 hours (30 minutes) late [{SECTION_KEY}] [DM-01].",
    )
    service, _ = _service(timecards, memos, corpus, params, FakeAdapter(outputs))
    result = service.run_timecard(_tc(timecards, "SC-03").id)
    assert result["status"] == "awaiting_decision", result.get("review_reason")


def test_prompts_forbid_unit_conversion_and_unlisted_numbers():
    text = prompts.SYSTEM_PROMPT.lower()
    assert "never calculate, convert units" in text
    assert "write no other number" in text
    assert "minutes_late in minutes, hours_late in hours" in text


# ---------- S2: no pseudo-references ----------


def test_pseudo_references_are_detected():
    text = (
        "Late [MEAL_PERIOD facts: hours_late] per [CGMA-2026.1-8.2] and [CGMA-2026.1-8.3, DM-01]."
    )
    assert pseudo_references(text) == ["[MEAL_PERIOD facts: hours_late]"]
    assert pseudo_references("[CGMA-2026.1-SCH-B]; [DM-01]") == []
    assert pseudo_references("see [note]") == ["[note]"]
    output = {"citation_keys": [], "explanation": "per [CGMA-2026.1-8.3, DM-01]"}
    assert cited_keys(output, "explanation") == ["CGMA-2026.1-8.3", "DM-01"]


def test_pseudo_reference_routes_to_review_and_valid_keys_pass(timecards, memos, corpus, params):
    bad = with_explanation(
        good_outputs(SECTION_KEY, "DM-01", "approve"),
        explanation=f"Late meal [{SECTION_KEY}] [MEAL_PERIOD facts: hours_late] [DM-01].",
    )
    service, store = _service(timecards, memos, corpus, params, FakeAdapter(bad))
    result = service.run_timecard(_tc(timecards, "SC-03").id)
    assert result["status"] == "needs_human_review"
    assert "bracketed text that is not a citation key" in result["review_reason"]
    statuses = {
        s["kind"]: s["validation_status"] for s in store.list_suggestions(result["case_id"])
    }
    assert statuses["explain"] == "invalid"

    good = with_explanation(
        good_outputs(SECTION_KEY, "DM-01", "approve"),
        explanation=f"Late meal [{SECTION_KEY}, DM-01].",
    )
    service, _ = _service(timecards, memos, corpus, params, FakeAdapter(good))
    assert service.run_timecard(_tc(timecards, "SC-03").id)["status"] == "awaiting_decision"


@pytest.mark.parametrize(
    "prose, status",
    [
        ("A second meal is due under CGMA-2026.1-8.4.", "CGMA-2026.1-8.4 not_provided"),
        ("Compare the terms in DM-03.", "DM-03 not_provided"),
        ("The rule is in CGMA-2026.1-8.21.", "CGMA-2026.1-8.21 unknown_key"),
    ],
)
def test_unbracketed_keys_are_validated_too(timecards, memos, corpus, params, prose, status):
    outputs = with_explanation(
        good_outputs(SECTION_KEY, "DM-01", "approve"),
        explanation=f"Late meal [{SECTION_KEY}] [DM-01]. {prose}",
    )
    service, _ = _service(timecards, memos, corpus, params, FakeAdapter(outputs))
    result = service.run_timecard(_tc(timecards, "SC-03").id)
    assert result["status"] == "needs_human_review"
    assert status in result["review_reason"]


@pytest.mark.parametrize(
    "change, reason",
    [
        ({"justification": "Per [CGMA-2026.1-99.9]."}, "CGMA-2026.1-99.9 unknown_key"),
        ({"justification": f"Late by 0.75 hours [{SECTION_KEY}]."}, "numbers not in"),
        ({"justification": f"See [policy row] [{SECTION_KEY}]."}, "not a citation key"),
        ({"requested_correction": "Fix it within 9 days."}, "numbers not in"),
    ],
)
def test_each_check_applies_to_the_proposal_part(timecards, memos, corpus, params, change, reason):
    outputs = with_proposal(good_outputs(SECTION_KEY, "DM-01", "approve"), **change)
    service, store = _service(timecards, memos, corpus, params, FakeAdapter(outputs))
    result = service.run_timecard(_tc(timecards, "SC-03").id)
    assert result["status"] == "needs_human_review"
    assert "propose: " in result["review_reason"] and reason in result["review_reason"]
    statuses = {
        s["kind"]: s["validation_status"] for s in store.list_suggestions(result["case_id"])
    }
    assert statuses == {"explain": "valid", "propose": "invalid"}


def test_citing_a_passage_that_was_not_sent_is_invalid(timecards, memos, corpus, params):
    outputs = with_explanation(
        good_outputs(SECTION_KEY, "DM-01", "approve"),
        explanation=f"Late meal [{SECTION_KEY}] [DM-01] [CGMA-2026.1-8.6].",
        citation_keys=[SECTION_KEY, "DM-01", "CGMA-2026.1-8.6"],
    )
    service, _ = _service(timecards, memos, corpus, params, FakeAdapter(outputs))
    result = service.run_timecard(_tc(timecards, "SC-03").id)
    assert result["status"] == "needs_human_review"
    assert "CGMA-2026.1-8.6 not_provided" in result["review_reason"]


# ---------- S3: the message is drafted for the human's action ----------


def test_return_on_an_approve_case_drafts_for_the_return(timecards, memos, corpus, params):
    """The gap found in the first real run: the message must match the human's action."""
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-01", "approve"))
    service, store = _service(timecards, memos, corpus, params, adapter)
    case_id = service.run_timecard(_tc(timecards, "SC-03").id)["case_id"]
    chosen = service.decide(case_id, {"action": "return", "actor": ACTOR})
    draft_request = adapter.requests[-1]
    assert draft_request.schema_name == "draft" and chosen_action(draft_request) == "return"
    assert '"policy_action":"approve"' in draft_request.messages[0].content
    assert chosen["draft"]["for_action"] == "return"


def test_draft_failure_marks_the_case_for_review_and_the_human_writes(
    timecards, memos, corpus, params
):
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-02", "return"), fail={"draft"})
    service, store = _service(timecards, memos, corpus, params, adapter)
    case_id = service.run_timecard(_tc(timecards, "SC-05").id)["case_id"]
    chosen = service.decide(case_id, {"action": "return", "actor": ACTOR})
    assert chosen["waiting_on"] == ["message_checkpoint"]
    assert chosen["draft"] is None and chosen["draft_status"] == "missing"
    assert chosen["status"] == "needs_human_review"  # constraint 7
    assert chosen["review_reason"].startswith("draft: LLM call failed")
    review = [a for a in store.list_audit(case_id) if a["entry_kind"] == "review"]
    assert review[-1]["payload"] == {
        "output": "draft",
        "reason": chosen["review_reason"],
        "facts_only": True,
    }
    outcome = service.confirm_message(case_id, {"actor": ACTOR, "message": "Please fix the meal."})
    assert outcome["status"] == "returned"
    assert store.return_messages[-1]["body"] == "Please fix the meal."
    executed = _decisions(store, case_id)[-1]["payload"]
    assert executed["message_source"] == "human_written" and executed["original_draft"] is None
    assert executed["case_status_before"] == "awaiting_decision"


@pytest.mark.parametrize(
    "change, reason",
    [
        ({"for_action": "escalate"}, "written for 'escalate'"),
        ({"recipient_role": "payroll_specialist"}, "does not fit a return"),
        ({"body": "Your meal was 45 minutes late [CGMA-2026.1-8.2]."}, "numbers not in"),
        ({"body": "See [the meal rule] [CGMA-2026.1-8.2]."}, "not a citation key"),
        ({"body": "See your deal memo [DM-02].", "citation_keys": ["DM-02"]}, "required missing"),
    ],
)
def test_invalid_draft_is_not_shown(timecards, memos, corpus, params, change, reason):
    outputs = good_outputs(SECTION_KEY, "DM-02", "return")
    draft = outputs["draft"]
    outputs["draft"] = lambda r: {**draft(r), **change}  # type: ignore[operator]
    service, store = _service(timecards, memos, corpus, params, FakeAdapter(outputs))
    case_id = service.run_timecard(_tc(timecards, "SC-05").id)["case_id"]
    chosen = service.decide(case_id, {"action": "return", "actor": ACTOR})
    assert chosen["draft"] is None and chosen["draft_status"] == "invalid"
    assert reason in chosen["review_reason"]
    assert service.case_detail(case_id)["draft"] is None


def test_cancel_returns_to_the_choice_and_is_audited(timecards, memos, corpus, params):
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-01", "approve"))
    service, store = _service(timecards, memos, corpus, params, adapter)
    case_id = service.run_timecard(_tc(timecards, "SC-03").id)["case_id"]
    service.decide(case_id, {"action": "return", "actor": ACTOR})
    with pytest.raises(DecisionError, match="confirmed by 'sam.verhoeven'"):
        service.confirm_message(case_id, {"actor": "kim", "message": "x"})
    back = service.confirm_message(case_id, {"actor": "kim", "cancel": True})  # any actor
    assert back["waiting_on"] == ["human_checkpoint"]
    detail = service.case_detail(case_id)
    assert detail["output_status"]["draft"] == "missing" and detail["draft"] is None
    assert detail["chosen_action"] is None and detail["cancelled_rounds"] == 1
    outcome = service.decide(case_id, {"action": "approve", "actor": "kim"})
    assert outcome["status"] == "approved" and store.return_messages == []
    stages = [(d["payload"]["stage"], d["actor"]) for d in _decisions(store, case_id)]
    assert stages == [
        ("action_chosen", ACTOR),
        ("message_cancelled", "kim"),
        ("executed", "kim"),
    ]
    executed = _decisions(store, case_id)[-1]["payload"]
    assert executed["cancelled_rounds"] == 1 and executed["original_draft"] is None
    assert executed["message"] is None


def test_draft_status_never_comes_from_a_cancelled_round(timecards, memos, corpus, params):
    calls = {"n": 0}
    outputs = good_outputs(SECTION_KEY, "DM-02", "return")
    good = outputs["draft"]

    def draft(request):
        calls["n"] += 1
        if calls["n"] == 2:
            return {"broken": True}  # second round does not match the schema
        return good(request)  # type: ignore[operator]

    outputs["draft"] = draft
    service, _ = _service(timecards, memos, corpus, params, FakeAdapter(outputs))
    case_id = service.run_timecard(_tc(timecards, "SC-05").id)["case_id"]
    assert service.decide(case_id, {"action": "return", "actor": ACTOR})["draft_status"] == "valid"
    service.confirm_message(case_id, {"actor": ACTOR, "cancel": True})
    second = service.decide(case_id, {"action": "return", "actor": ACTOR})
    assert second["draft_status"] == "missing" and second["draft"] is None
    assert "draft: output did not match the schema" in second["review_reason"]


def test_wrong_endpoint_and_message_on_decide_are_refused(timecards, memos, corpus, params):
    service, store = _service(
        timecards, memos, corpus, params, FakeAdapter(good_outputs(SECTION_KEY, "DM-02", "return"))
    )
    case_id = service.run_timecard(_tc(timecards, "SC-05").id)["case_id"]
    with pytest.raises(DecisionError, match="message is confirmed after"):
        service.decide(case_id, {"action": "return", "actor": ACTOR, "message": "x"})
    with pytest.raises(CaseNotWaiting, match="waits for the action"):
        service.confirm_message(case_id, {"actor": ACTOR, "message": "x"})
    service.decide(case_id, {"action": "return", "actor": ACTOR})
    with pytest.raises(CaseNotWaiting, match="waits for the message"):
        service.decide(case_id, {"action": "approve", "actor": ACTOR})
    with pytest.raises(DecisionError, match="exclusive"):
        service.confirm_message(case_id, {"actor": ACTOR, "cancel": True, "message": "x"})
    with pytest.raises(DecisionError, match="goes to one of"):
        service.confirm_message(
            case_id, {"actor": ACTOR, "message": "x", "recipient_role": "payroll_specialist"}
        )
    assert store.decisions == []


class _AuditFailsOnce(MemoryStore):
    """Fails the first `action_chosen` audit write, after the resume value was accepted."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.failed = False

    def add_audit(self, case_id, entry_kind, actor, payload):
        if not self.failed and payload.get("stage") == "action_chosen":
            self.failed = True
            raise RuntimeError("audit unavailable")
        return super().add_audit(case_id, entry_kind, actor, payload)


def test_stalled_checkpoint_resumes_only_with_the_accepted_choice(timecards, memos, corpus, params):
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-02", "return"))
    service, store = _service(timecards, memos, corpus, params, adapter, _AuditFailsOnce)
    case_id = service.run_timecard(_tc(timecards, "SC-05").id)["case_id"]
    with pytest.raises(RuntimeError, match="audit unavailable"):
        service.decide(case_id, {"action": "return", "actor": ACTOR})
    with pytest.raises(CaseNotWaiting, match="already accepted"):
        service.decide(case_id, {"action": "approve", "actor": ACTOR})
    retried = service.decide(case_id, {"action": "return", "actor": ACTOR})
    assert retried["waiting_on"] == ["message_checkpoint"]
    assert [d["payload"]["stage"] for d in _decisions(store, case_id)] == ["action_chosen"]


def test_a_second_execution_writes_nothing(timecards, memos, corpus, params):
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-01", "approve"))
    service, store = _service(timecards, memos, corpus, params, adapter)
    case_id = service.run_timecard(_tc(timecards, "SC-03").id)["case_id"]
    store.set_case_status(case_id, "approved", None)  # executed elsewhere meanwhile
    outcome = service.decide(case_id, {"action": "approve", "actor": ACTOR})
    assert outcome["execution"] == {"already_executed": True, "case_status": "approved"}
    assert store.decisions == [] and store.premium_lines == []
    assert [d["payload"]["stage"] for d in _decisions(store, case_id)] == ["duplicate_attempt"]


# ---------- S4: token efficiency ----------


def test_dry_run_estimates_are_within_the_budget():
    approve = dry_run("SC-03", "approve", 1200)
    assert approve["llm_calls"] == 1 and approve["per_call"][0]["node"] == "explain_propose"
    assert approve["passages_sent"] == [
        SECTION_KEY,
        "CGMA-2026.1-8.3",
        "CGMA-2026.1-SCH-B",
        "DM-01",
    ]
    ret = dry_run("SC-05", "return", 1200)
    assert [c["node"] for c in ret["per_call"]] == ["explain_propose", "draft"]
    # Iteration 2 measured about 3,100 to 3,500 input tokens per call, three calls per case.
    assert approve["input_tokens_per_case"] < 2500
    assert ret["input_tokens_per_case"] < 4500
    assert dry_run("SC-01", "approve", 1200)["clean"] is True


def test_passages_sent_cover_the_expected_keys_of_every_wired_case():
    for case in build_manifest()["cases"]:
        if case["negative"] or case["expected_rules"] != ["MEAL_PERIOD"]:
            continue  # only MEAL_PERIOD is wired in the engine (Iteration 5 adds the rest)
        report = dry_run(case["scenario_id"], case["expected_action"], 1200)
        expected = set(case["expected_citation_keys"]) | {case["deal_memo_id"]}
        assert expected <= set(report["passages_sent"]), case["id"]


def test_dry_run_builds_the_same_request_as_the_node(timecards, memos, corpus, params):
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-01", "approve"))
    service, _ = _service(timecards, memos, corpus, params, adapter)
    service.run_timecard(_tc(timecards, "SC-03").id)
    _, _, requests = dry_run_requests("SC-03", "approve", 1200)
    sent, built = adapter.requests[0], requests[0]
    assert built.system == sent.system and built.messages == sent.messages
    assert built.response_schema == sent.response_schema
    assert built.max_output_tokens == sent.max_output_tokens


def test_resume_channel_matches_the_library():
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langgraph.constants import RESUME
    assert RESUME == _RESUME_CHANNEL


class _CommitsThenFails(MemoryStore):
    """apply_execution commits, then the step fails once (lost checkpoint after the commit)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.failed = False

    def apply_execution(self, plan):
        effects = super().apply_execution(plan)
        if not self.failed:
            self.failed = True
            raise RuntimeError("checkpoint lost after commit")
        return effects


def test_retry_after_a_committed_execution_keeps_one_executed_entry(
    timecards, memos, corpus, params
):
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-02", "return"))
    service, store = _service(timecards, memos, corpus, params, adapter, _CommitsThenFails)
    case_id = service.run_timecard(_tc(timecards, "SC-05").id)["case_id"]
    service.decide(case_id, {"action": "return", "actor": ACTOR})
    with pytest.raises(RuntimeError, match="checkpoint lost"):
        service.confirm_message(case_id, {"actor": ACTOR, "message": "Please fix the meal."})
    with pytest.raises(CaseNotWaiting, match="already holds the decision"):
        service.confirm_message(case_id, {"actor": ACTOR, "message": "Another text."})
    outcome = service.confirm_message(case_id, {"actor": ACTOR, "message": "Please fix the meal."})
    assert outcome["retried_execution"] is True
    assert len(store.decisions) == 1 and len(store.return_messages) == 1
    stages = [d["payload"]["stage"] for d in _decisions(store, case_id)]
    assert stages == ["action_chosen", "executed", "duplicate_attempt"]
    executed = _decisions(store, case_id)[1]["payload"]
    assert executed["message"] == "Please fix the meal." and executed["original_draft"]


class _CancelAuditFailsOnce(MemoryStore):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.failed = False

    def add_audit(self, case_id, entry_kind, actor, payload):
        if not self.failed and payload.get("stage") == "message_cancelled":
            self.failed = True
            raise RuntimeError("audit unavailable")
        return super().add_audit(case_id, entry_kind, actor, payload)


def test_stalled_cancel_resumes_only_with_the_same_cancel(timecards, memos, corpus, params):
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-02", "return"))
    service, store = _service(timecards, memos, corpus, params, adapter, _CancelAuditFailsOnce)
    case_id = service.run_timecard(_tc(timecards, "SC-05").id)["case_id"]
    service.decide(case_id, {"action": "return", "actor": ACTOR})
    with pytest.raises(RuntimeError, match="audit unavailable"):
        service.confirm_message(case_id, {"actor": "kim", "cancel": True})
    with pytest.raises(CaseNotWaiting, match="already accepted"):
        service.confirm_message(case_id, {"actor": ACTOR, "message": "x"})
    back = service.confirm_message(case_id, {"actor": "kim", "cancel": True})
    assert back["waiting_on"] == ["human_checkpoint"]
    stages = [d["payload"]["stage"] for d in _decisions(store, case_id)]
    assert stages == ["action_chosen", "message_cancelled"]


def test_prompts_are_compact_and_estimates_are_deterministic(timecards, memos, corpus, params):
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-01", "approve"))
    service, _ = _service(timecards, memos, corpus, params, adapter)
    service.run_timecard(_tc(timecards, "SC-03").id)
    request = adapter.requests[0]
    content = request.messages[0].content
    assert '": ' not in content and "\n  " not in content  # no indentation, compact JSON
    # fact meanings and units listed once per rule
    assert content.count("MEAL_PERIOD.hours_late (hours):") == 1
    assert request.max_output_tokens == 2 * 1200  # the merged call returns two outputs
    assert estimate_request(request) == estimate_request(request)
    assert "title" not in str(prompts.strict_schema(prompts.ExplainProposeOutput))


# ---------- S8: unit and clock-time meaning check ----------

# The sentence of the author's S6 run (2026-10-14): 12.0 is the clock time of meal out (12:00),
# hours to meal was 5.0. The stray-number check passed it because 12.0 was in the case data (meal
# out in decimal hours) and still passes it whenever a cited passage holds a 12; only the unit
# check reads what the number means.
S6_SENTENCE = "the meal out at 12.0 minutes after Call"


def test_prompts_show_times_of_day_in_hh_mm_and_fact_units(timecards, memos, corpus, params):
    adapter = FakeAdapter(good_outputs(SECTION_KEY, "DM-02", "return"))
    service, _ = _service(timecards, memos, corpus, params, adapter)
    case_id = service.run_timecard(_tc(timecards, "SC-05").id)["case_id"]
    service.decide(case_id, {"action": "return", "actor": ACTOR})
    assert adapter.kinds() == ["explain_propose", "draft"]
    for request in adapter.requests:
        content = request.messages[0].content
        assert '"times_of_day":{"call":"07:00","meal_out":"12:00","meal_in":"12:24"' in content
        assert '"meal_out":12.0' not in content and '"meal_in":12.4' not in content
        assert "MEAL_PERIOD.hours_to_meal (hours):" in content
        assert "MEAL_PERIOD.meal_minutes (minutes):" in content
    assert "times of day (hh:mm), not durations" in prompts.SYSTEM_PROMPT.lower()


def test_unit_numbers_are_read_with_their_unit():
    text = (
        "A 30-minute meal, 0.5 hour late, 1,200 minutes, 6.0 Hours, 30 min, 6 hrs, 2 hr; "
        "not 12:30 minutes or DM-02."
    )
    assert [(str(v), u) for v, u, _ in unit_numbers(text)] == [
        ("30", "minutes"),
        ("0.5", "hours"),
        ("1200", "minutes"),
        ("6.0", "hours"),
        ("30", "minutes"),
        ("6", "hours"),
        ("2", "hours"),
    ]
    assert clock_times_with_unit(text) == ["12:30 minutes"]
    # No space, a lone "h" and Unicode hyphens (non-breaking hyphen, en dash) are read too.
    other = f"12.0min, 6 h, 12{chr(0x2011)}minute, 5{chr(0x2013)}hour"
    assert [(str(v), u) for v, u, _ in unit_numbers(other)] == [
        ("12.0", "minutes"),
        ("6", "hours"),
        ("12", "minutes"),
        ("5", "hours"),
    ]
    # Words and identifiers that are not units stay unread.
    assert unit_numbers("30 minimum, 6 hourly, the 8th day, SC-05h, EMP-1001h, 5 hands") == []


def test_a_unit_number_is_allowed_by_a_sent_passage_with_that_unit_only():
    passage = {
        "citation_key": "P-1",
        "heading": "Rest",
        "body": "not less than 10.0 hours between Wrap and Call",
    }
    state = {"findings": [], "case": {}, "chunks": [passage], "passage_keys": ["P-1"]}
    assert unit_mismatches("a rest of 10.0 hours", state) == []
    assert unit_mismatches("a rest of 10.0 minutes", state) == ["10.0 minutes"]
    assert unit_mismatches("a rest of 10.0 hours", {**state, "passage_keys": []}) == ["10.0 hours"]


def test_the_s6_sentence_fails_the_meaning_check_and_clock_times_allow_no_bare_number(
    timecards, memos, params
):
    tc = _tc(timecards, "SC-05")
    clock = demo_clock()
    findings = [
        f.to_dict()
        for f in detect(tc, memos["DM-02"], params, clock.as_of, clock.payroll_run_date).findings
    ]
    case = build_case(tc, memos["DM-02"], findings, clock.payroll_run_date, "2026.1")
    state = {"findings": findings, "case": case, "chunks": []}
    assert findings[0]["facts"]["hours_to_meal"] == 5.0
    assert unit_mismatches(S6_SENTENCE, state) == ["12.0 minutes"]  # meaning: no such fact
    # Presence: 12:00 no longer allows a bare 12, so with the case data alone 12.0 is stray too.
    assert stray_numbers(S6_SENTENCE, state) == ["12.0"]
    assert unknown_clock_times("meal out at 12:00, meal in at 12:24", state) == []
    assert unknown_clock_times("meal out at 13:15", state) == ["13:15"]
    assert unknown_clock_times("meal out at 12:00:00, not 13:15:00", state) == ["13:15"]
    # A clock time allows no bare number: "12.0" with no unit is a stray number, "12:00" is not.
    assert stray_numbers("the meal out at 12.0 after Call", state) == ["12.0"]
    assert stray_numbers("the meal out at 12:00, meal in at 12:24", state) == []


def _sc05_draft(body):
    outputs = good_outputs(SECTION_KEY, "DM-02", "return")
    draft = outputs["draft"]
    outputs["draft"] = lambda r: {**draft(r), "body": body}  # type: ignore[operator]
    return outputs


# The same error in the HH:MM form the prompts now use: passes the clock and presence checks.
S6_SENTENCE_HH_MM = "the meal out at 12:00 minutes after Call"


@pytest.mark.parametrize(
    "sentence, check, written",
    [
        (S6_SENTENCE, "numbers with a unit that match no fact or sent passage", "'12.0 minutes'"),
        (S6_SENTENCE_HH_MM, "clock times written as durations", "'12:00 minutes'"),
    ],
)
@pytest.mark.parametrize("part", ["explanation", "proposal", "draft"])
def test_the_s6_sentence_routes_to_review_in_every_output(
    timecards, memos, corpus, params, part, sentence, check, written
):
    text = f"Per the timecard, {sentence} [{SECTION_KEY}]."
    outputs = good_outputs(SECTION_KEY, "DM-02", "return")
    if part == "explanation":
        outputs = with_explanation(outputs, explanation=f"{text} [DM-02]")
    elif part == "proposal":
        outputs = with_proposal(outputs, justification=text)
    else:
        outputs = _sc05_draft(text)
    service, _ = _service(timecards, memos, corpus, params, FakeAdapter(outputs))
    result = service.run_timecard(_tc(timecards, "SC-05").id)
    if part == "draft":
        assert result["status"] == "awaiting_decision", result.get("review_reason")
        result = service.decide(result["case_id"], {"action": "return", "actor": ACTOR})
        assert result["draft"] is None and result["draft_status"] == "invalid"
    kind = {"explanation": "explain", "proposal": "propose", "draft": "draft"}[part]
    assert result["status"] == "needs_human_review"
    reason = result["review_reason"]
    assert f"{kind}: {check}" in reason
    assert written in reason


def test_correct_units_and_clock_times_pass(timecards, memos, corpus, params):
    # Agreement values from the YAML ("30 minutes", "6.0 hours" today); 24, 5.0, 0.5, 30 and 6.5 are
    # the scenarios' facts.
    minimum, deadline = params.meal.min_duration_minutes, params.meal.deadline_hours
    sc05 = (
        f"Meal out was at 12:00 and meal in at 12:24, a meal of 24 minutes, shorter than the "
        f"{minimum} minutes required; it began 5.0 hours after call, within {deadline} hours "
        f"[{SECTION_KEY}] [DM-02]."
    )
    draft = (
        f"Your 24-minute meal on 2026-03-11 (12:00 to 12:24) is under {minimum} minutes "
        f"[{SECTION_KEY}]."
    )
    outputs = _sc05_draft(draft)
    outputs = with_explanation(outputs, explanation=sc05)
    outputs = with_proposal(outputs, justification=f"A 24-minute meal [{SECTION_KEY}].")
    service, _ = _service(timecards, memos, corpus, params, FakeAdapter(outputs))
    result = service.run_timecard(_tc(timecards, "SC-05").id)
    assert result["status"] == "awaiting_decision", result.get("review_reason")
    chosen = service.decide(result["case_id"], {"action": "return", "actor": ACTOR})
    assert chosen["draft_status"] == "valid", chosen.get("review_reason")

    sc03 = (
        f"The meal began 0.5 hour (30 minutes) late, 6.5 hours after call [{SECTION_KEY}] [DM-01]."
    )
    outputs = with_explanation(good_outputs(SECTION_KEY, "DM-01", "approve"), explanation=sc03)
    service, _ = _service(timecards, memos, corpus, params, FakeAdapter(outputs))
    result = service.run_timecard(_tc(timecards, "SC-03").id)
    assert result["status"] == "awaiting_decision", result.get("review_reason")


@pytest.mark.parametrize(
    "sentence, reason",
    [
        ("Meal out was at 13:15", "clock times that are not a timecard event of the case: "),
        ("The penalty is 99.99 USD", "numbers not in the facts or passages: ['99.99']"),
    ],
)
def test_unknown_clock_times_and_stray_numbers_still_route(
    timecards, memos, corpus, params, sentence, reason
):
    outputs = with_explanation(
        good_outputs(SECTION_KEY, "DM-02", "return"),
        explanation=f"{sentence} [{SECTION_KEY}] [DM-02].",
    )
    service, _ = _service(timecards, memos, corpus, params, FakeAdapter(outputs))
    result = service.run_timecard(_tc(timecards, "SC-05").id)
    assert result["status"] == "needs_human_review"
    assert f"explain: {reason}" in result["review_reason"]
