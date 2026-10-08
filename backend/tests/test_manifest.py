"""Tests for the evaluation case manifest (P1.I1.S6)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from payroll_triage import calc
from payroll_triage.corpus.render import citation_keys_in, render_agreement
from payroll_triage.data.scenarios import load_catalog
from payroll_triage.evals.manifest import build_manifest, check_manifest, load_manifest
from payroll_triage.params import load_parameters


@pytest.fixture(scope="module")
def params():
    return load_parameters()


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def manifest(catalog, params):
    from payroll_triage.corpus.deal_memos import load_deal_memos

    return build_manifest(catalog, params=params, memos=load_deal_memos())


@pytest.fixture(scope="module")
def cases(manifest):
    return {c["id"]: c for c in manifest["cases"]}


def test_committed_manifest_is_current(manifest):
    assert check_manifest(manifest) == [], "run `uv run ptc build-manifest` and commit the result"
    assert load_manifest()["counts"] == manifest["counts"]


def test_eighteen_cases_with_negatives(manifest, cases):
    assert manifest["counts"] == {"cases": 18, "positive": 16, "negative": 2}
    assert list(cases) == [f"EV-{i:02d}" for i in range(1, 19)]
    assert {c["scenario_id"] for c in cases.values() if c["negative"]} == {"SC-01", "SC-02"}
    for c in cases.values():
        if c["negative"]:
            assert c["expected_action"] == "none" and c["expected_findings"] == []
        else:
            assert c["expected_action"] in ("approve", "return", "escalate")
            assert c["expected_findings"]


def test_expectations_match_catalog(cases, catalog):
    for s in catalog.scenarios:
        c = cases["EV-" + s.id.split("-")[1]]
        assert c["expected_rules"] == sorted(set(s.expected_rules))
        assert c["expected_action"] == s.expected_action
        assert c["deal_memo_id"] == s.deal_memo
        assert c["week_ending"] == s.week_ending.isoformat()


def test_citation_keys_resolve_to_agreement_headings(manifest, params):
    keys = set(citation_keys_in(render_agreement(params)))
    for c in manifest["cases"]:
        for key in c["expected_citation_keys"]:
            assert key in keys, (c["id"], key)
            assert key.startswith(params.agreement.citation_prefix + "-")
        for f in c["expected_findings"]:
            assert f["citation_keys"][0] == params.citation_key(f["section"])
            assert f["section"] == params.rule(f["rule_id"]).section


def test_version_in_force_for_every_week_ending(manifest, params):
    import datetime as dt

    for c in manifest["cases"]:
        we = dt.date.fromisoformat(c["week_ending"])
        assert params.agreement.in_force_on(we)
        assert c["agreement_version_in_force"] == params.agreement.version


def test_meal_facts_follow_parameters(cases, params):
    sched = params.meal.penalty_schedule_usd
    f03 = cases["EV-03"]["expected_findings"][0]
    assert f03["rule_id"] == "MEAL_PERIOD" and f03["policy_action"] == "approve"
    assert f03["facts"]["increments"] == 1
    assert Decimal(f03["facts"]["penalty_usd"]) == sched[0]
    f04 = [f for f in cases["EV-04"]["expected_findings"] if f["rule_id"] == "MEAL_PERIOD"]
    assert len(f04) == 2
    for f in f04:
        assert f["facts"]["increments"] == 3
        assert Decimal(f["facts"]["penalty_usd"]) == calc.meal_penalty_amount(3, params)
    f05 = cases["EV-05"]["expected_findings"][0]
    assert f05["facts"]["is_short"] is True and f05["policy_action"] == "return"
    assert f05["facts"]["meal_minutes"] < params.meal.min_duration_minutes
    f14 = [f for f in cases["EV-14"]["expected_findings"] if f["rule_id"] == "MEAL_PERIOD"][0]
    assert f14["facts"]["increments"] == 2
    assert Decimal(f14["facts"]["penalty_usd"]) == sched[0] + sched[1]


def test_extended_and_rest_facts_follow_parameters(cases, params):
    f09 = cases["EV-09"]["expected_findings"][0]
    assert f09["rule_id"] == "EXTENDED_DAY"
    assert f09["facts"]["hours_over_threshold"] == pytest.approx(
        13.5 - params.extended_day.threshold_hours
    )
    assert Decimal(f09["facts"]["premium_usd"]) == calc.premium_amount(
        f09["facts"]["hours_over_threshold"],
        Decimal(f09["facts"]["hourly_rate_usd"]),
        params.extended_day.multiplier,
    )
    f11 = cases["EV-11"]["expected_findings"][0]
    assert f11["rule_id"] == "REST_PERIOD"
    assert f11["facts"]["rest_hours"] == pytest.approx(8.5)
    assert f11["facts"]["invaded_hours"] == pytest.approx(params.rest.min_hours - 8.5)
    f12 = cases["EV-12"]["expected_findings"][0]
    assert f12["facts"]["previous_wrap"] > 24


def test_scale_and_eligibility_facts(cases, params, catalog):
    f13 = cases["EV-13"]["expected_findings"][0]
    assert f13["rule_id"] == "SCALE_RATE" and f13["policy_action"] == "escalate"
    assert Decimal(f13["facts"]["scale_usd"]) == params.scale_for("6305").hourly_scale_usd
    assert Decimal(f13["facts"]["shortfall_per_hour_usd"]) > 0
    f15 = cases["EV-15"]["expected_findings"][0]
    assert f15["rule_id"] == "ELIGIBILITY_DOC"
    import datetime as dt

    start = dt.date.fromisoformat(f15["facts"]["first_day_of_work"])
    deadline = calc.add_business_days(start, params.eligibility.deadline_business_days)
    assert f15["facts"]["deadline_date"] == deadline.isoformat()
    assert f15["facts"]["business_days_overdue"] == calc.business_days_between(
        deadline, catalog.as_of_date
    )


def test_multiple_findings_take_most_severe(cases):
    assert {f["rule_id"] for f in cases["EV-14"]["expected_findings"]} == {
        "SCALE_RATE",
        "MEAL_PERIOD",
    }
    assert cases["EV-14"]["expected_action"] == "escalate"
    assert cases["EV-16"]["expected_action"] == "escalate"
    assert {f["policy_action"] for f in cases["EV-17"]["expected_findings"]} == {
        "approve",
        "return",
    }
    assert cases["EV-17"]["expected_action"] == "return"
    assert cases["EV-18"]["expected_action"] == "return"
