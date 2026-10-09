"""Rule engine (MEAL_PERIOD) tested against the committed eval manifest and the policy."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from payroll_triage.corpus.deal_memos import load_deal_memos
from payroll_triage.data.generator import load_generated_timecards
from payroll_triage.data.scenarios import load_catalog
from payroll_triage.engine import detect, wired_rules
from payroll_triage.engine.facts import FACTS_MODELS, MealPeriodFacts
from payroll_triage.engine.priority import PriorityInputs, amount_tier, is_urgent, priority_score
from payroll_triage.engine.rules import Finding
from payroll_triage.evals.manifest import load_manifest
from payroll_triage.params import load_parameters


@pytest.fixture(scope="module")
def params():
    return load_parameters()


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def memos():
    memos = load_deal_memos()
    import json

    from payroll_triage.corpus.deal_memos import parse_deal_memo
    from payroll_triage.paths import generated_dir

    with (generated_dir() / "filler-deal-memos.json").open(encoding="utf-8") as fh:
        for raw in json.load(fh)["deal_memos"]:
            memos[raw["id"]] = parse_deal_memo(raw)
    return memos


@pytest.fixture(scope="module")
def timecards():
    return {t.id: t for t in load_generated_timecards()}


@pytest.fixture(scope="module")
def cases():
    return {c["scenario_id"]: c for c in load_manifest()["cases"]}


def _run(tc, memos, params, catalog):
    return detect(
        tc,
        memos[tc.deal_memo_id],
        params,
        catalog.as_of_date,
        catalog.payroll_run_date,
        catalog.holidays,
        catalog.labels["day_type"]["work"],
    )


def test_only_meal_period_is_wired_in_iteration_2():
    assert wired_rules() == ("MEAL_PERIOD",)
    assert set(FACTS_MODELS) == {"MEAL_PERIOD"}


def test_engine_reproduces_manifest_meal_findings(timecards, memos, params, catalog, cases):
    """For every case: the engine's MEAL_PERIOD findings equal the manifest's, fact by fact."""
    checked = 0
    for scenario_id, case in cases.items():
        tc = timecards[case["timecard_id"]]
        det = _run(tc, memos, params, catalog)
        expected = [f for f in case["expected_findings"] if f["rule_id"] == "MEAL_PERIOD"]
        got = [f for f in det.findings if f.rule_id == "MEAL_PERIOD"]
        assert len(got) == len(expected), scenario_id
        for g, e in zip(got, expected, strict=True):
            assert g.section == e["section"]
            assert list(g.citation_keys) == e["citation_keys"]
            assert g.policy_action == e["policy_action"]
            assert g.day_date.isoformat() == e["day_date"]
            assert g.facts == e["facts"], (scenario_id, g.facts, e["facts"])
            checked += 1
    assert checked >= 6  # SC-03, SC-04 (two days), SC-05, SC-14, SC-17, SC-18


def test_showcase_cases_actions_and_amounts(timecards, memos, params, catalog, cases):
    sc03 = _run(timecards[cases["SC-03"]["timecard_id"]], memos, params, catalog)
    assert sc03.policy_action == "approve" and len(sc03.findings) == 1
    f = sc03.findings[0]
    assert f.facts["increments"] == 1
    assert Decimal(f.facts["penalty_usd"]) == params.meal.penalty_schedule_usd[0]
    assert sc03.amount_usd == params.meal.penalty_schedule_usd[0]

    sc04 = _run(timecards[cases["SC-04"]["timecard_id"]], memos, params, catalog)
    assert sc04.policy_action == "approve" and len(sc04.findings) == 2
    per_day = sum(params.meal.penalty_schedule_usd[:3])
    assert all(f.facts["increments"] == 3 for f in sc04.findings)
    assert sc04.amount_usd == per_day * 2

    sc05 = _run(timecards[cases["SC-05"]["timecard_id"]], memos, params, catalog)
    assert sc05.policy_action == "return" and len(sc05.findings) == 1
    assert sc05.findings[0].facts["is_short"] is True
    assert sc05.amount_usd == Decimal("0.00")


def test_clean_weeks_and_filler_produce_no_finding(timecards, memos, params, catalog):
    for tc in timecards.values():
        if tc.scenario_id in ("SC-01", "SC-02") or tc.scenario_id.startswith("SC-F"):
            det = _run(tc, memos, params, catalog)
            assert det.findings == () and det.policy_action == "none"
            assert det.priority_score == 0


def test_facts_keys_match_manifest_schema(cases):
    manifest_keys = set(cases["SC-03"]["expected_findings"][0]["facts"])
    assert set(MealPeriodFacts.model_fields) == manifest_keys


def test_finding_round_trip(timecards, memos, params, catalog, cases):
    det = _run(timecards[cases["SC-03"]["timecard_id"]], memos, params, catalog)
    f = det.findings[0]
    assert Finding.from_dict(f.to_dict()) == f


def test_priority_formula_from_yaml(params, catalog):
    q = params.queue
    thresholds = q.amount_tier_thresholds_usd
    assert amount_tier(thresholds[0] - Decimal("0.01"), params) == 0
    assert amount_tier(thresholds[0], params) == 1
    assert amount_tier(thresholds[-1], params) == len(thresholds)
    assert is_urgent(catalog.as_of_date, catalog.payroll_run_date, params)
    assert not is_urgent(catalog.as_of_date, catalog.as_of_date + dt.timedelta(days=14), params)

    base = PriorityInputs(
        policy_action="approve",
        amount_usd=Decimal("0.00"),
        week_ending=catalog.as_of_date,
        as_of=catalog.as_of_date,
        payroll_run_date=catalog.as_of_date + dt.timedelta(days=14),
    )
    assert priority_score(base, params) == q.severity_weight * 1
    urgent = PriorityInputs(**{**base.__dict__, "payroll_run_date": catalog.payroll_run_date})
    assert priority_score(urgent, params) == q.urgency_weight + q.severity_weight
    escalate = PriorityInputs(**{**base.__dict__, "policy_action": "escalate"})
    assert priority_score(escalate, params) == q.severity_weight * 3
    old = PriorityInputs(
        **{**base.__dict__, "week_ending": catalog.as_of_date - dt.timedelta(days=60)}
    )
    assert priority_score(old, params) == q.severity_weight + q.max_days_late_points


def test_priority_orders_showcase_week(timecards, memos, params, catalog, cases):
    """On the demo week the return case (SC-05) outranks the approve case (SC-03)."""
    sc03 = _run(timecards[cases["SC-03"]["timecard_id"]], memos, params, catalog)
    sc05 = _run(timecards[cases["SC-05"]["timecard_id"]], memos, params, catalog)
    assert sc05.priority_score > sc03.priority_score
