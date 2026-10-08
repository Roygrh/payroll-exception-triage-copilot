"""Tests for the scenario catalog and the seeded generator (P1.I1.S5)."""

from __future__ import annotations

import datetime as dt

import pytest

from payroll_triage.corpus.deal_memos import load_deal_memos
from payroll_triage.data.generator import (
    check_generated,
    generate,
    timecards_document,
)
from payroll_triage.data.scenarios import WEEKDAYS, load_catalog
from payroll_triage.evals.expectations import combined_action, expected_findings
from payroll_triage.params import load_parameters


@pytest.fixture(scope="module")
def params():
    return load_parameters()


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def memos():
    return load_deal_memos()


@pytest.fixture(scope="module")
def data(catalog, memos, params):
    return generate(catalog, memos, params)


def test_catalog_matches_domain_model_counts(catalog):
    assert len(catalog.scenarios) == 18
    assert [s.id for s in catalog.scenarios] == [f"SC-{i:02d}" for i in range(1, 19)]
    categories = {}
    for s in catalog.scenarios:
        categories[s.category] = categories.get(s.category, 0) + 1
    assert categories == {
        "clean": 2,
        "late_meal": 2,
        "short_meal": 1,
        "missing_punch": 3,
        "extended_day": 2,
        "rest_period": 2,
        "scale_rate": 2,
        "eligibility": 2,
        "multiple": 2,
    }
    assert len(catalog.filler) == 4


def test_same_seed_is_identical_and_other_seed_differs(catalog, memos, params):
    a = timecards_document(generate(catalog, memos, params))
    b = timecards_document(generate(catalog, memos, params))
    assert a == b
    c = timecards_document(generate(catalog, memos, params, seed=catalog.seed + 1))
    assert c != a
    # Scenario timecards do not depend on the seed; only filler does.
    sa = [
        t
        for t in a["timecards"]
        if t["scenario_id"].startswith("SC-") and "-F" not in t["scenario_id"]
    ]
    sc = [
        t
        for t in c["timecards"]
        if t["scenario_id"].startswith("SC-") and "-F" not in t["scenario_id"]
    ]
    assert sa == sc


def test_committed_output_is_current(data):
    assert check_generated(data) == [], "run `uv run ptc generate-data` and commit the result"


def test_one_timecard_per_employee_per_week(data):
    keys = [(t.employee_id, t.week_ending) for t in data.timecards]
    assert len(keys) == len(set(keys))
    assert len(data.timecards) == 22
    assert all(t.week_ending.weekday() == 5 for t in data.timecards)
    assert all(t.producer_week == t.week_ending - dt.timedelta(days=6) for t in data.timecards)
    assert all([d.weekday for d in t.days] == list(WEEKDAYS) for t in data.timecards)


def test_week_endings_not_before_start_date(data, memos):
    for t in data.timecards:
        if t.deal_memo_id in memos:
            assert t.week_ending >= memos[t.deal_memo_id].start_date


def test_times_are_tenths(data):
    for t in data.timecards:
        for d in t.days:
            for v in (d.call, d.meal_out, d.meal_in, d.wrap):
                if v is not None:
                    assert abs(v * 10 - round(v * 10)) < 1e-9, (t.id, d.date, v)


def test_each_scenario_trigger_holds_by_construction(data, catalog, memos, params):
    by_scenario = {t.scenario_id: t for t in data.timecards}
    for s in catalog.scenarios:
        tc = by_scenario[s.id]
        findings = expected_findings(
            tc, memos[s.deal_memo], params, catalog.as_of_date, catalog.holidays
        )
        rules = sorted({f.rule_id for f in findings})
        assert rules == sorted(set(s.expected_rules)), (s.id, rules)
        assert combined_action(findings) == s.expected_action, s.id


def test_clean_weeks_and_filler_have_no_trigger(data, catalog, memos, params):
    filler_memos = {m.id: m for m in data.filler_deal_memos}
    for t in data.timecards:
        memo = memos.get(t.deal_memo_id) or filler_memos[t.deal_memo_id]
        findings = expected_findings(t, memo, params, catalog.as_of_date, catalog.holidays)
        if t.scenario_id in ("SC-01", "SC-02") or t.scenario_id.startswith("SC-F"):
            assert findings == [], t.scenario_id


def test_specific_construction_values(data, params):
    by = {t.scenario_id: t for t in data.timecards}
    sc03 = next(d for d in by["SC-03"].days if d.weekday == "Tue")
    assert sc03.meal_out - sc03.call == pytest.approx(6.5)
    sc05 = next(d for d in by["SC-05"].days if d.weekday == "Wed")
    assert round((sc05.meal_in - sc05.meal_out) * 60) == 24
    sc06 = next(d for d in by["SC-06"].days if d.weekday == "Wed")
    assert sc06.wrap is None and sc06.call is not None
    sc08 = next(d for d in by["SC-08"].days if d.weekday == "Tue")
    assert sc08.wrap < sc08.call
    sc09 = next(d for d in by["SC-09"].days if d.weekday == "Wed")
    assert (sc09.wrap - sc09.call) - (sc09.meal_in - sc09.meal_out) == pytest.approx(13.5)
    sc11 = by["SC-11"].days
    assert sc11[1].call + 24 - sc11[0].wrap == pytest.approx(8.5)
    sc12 = by["SC-12"].days
    assert sc12[0].wrap > 24 and sc12[1].call + 24 - sc12[0].wrap == pytest.approx(9.5)


def test_filler_memos_are_at_scale(data, params):
    assert len(data.filler_deal_memos) == 4
    for m in data.filler_deal_memos:
        assert m.hourly_rate_usd == params.scale_for(m.occupation_code).hourly_scale_usd
        assert m.scale_relationship == "at"
        assert m.eligibility_status == "completed"


def test_overtime_week_has_no_finding(data, catalog, memos, params):
    tc = next(t for t in data.timecards if t.scenario_id == "SC-02")
    for d in tc.days:
        worked = (d.wrap - d.call) - (d.meal_in - d.meal_out)
        assert worked > params.overtime.daily_after_hours
        assert worked < params.extended_day.threshold_hours
    assert expected_findings(tc, memos["DM-06"], params, catalog.as_of_date) == []


def test_guards_reject_bad_inputs(catalog, memos, params):
    import dataclasses
    import datetime as dt
    import random

    from payroll_triage.data.generator import _filler_day, build_day, build_scenario_timecard
    from payroll_triage.data.scenarios import DaySpec, FillerJitter

    unit = params.payroll.time_unit_hours
    with pytest.raises(ValueError, match="time unit"):
        build_day(
            DaySpec(kind="long_day", hours_worked=13.0 + unit / 2),
            dt.date(2026, 3, 9),
            "Mon",
            catalog,
            params,
        )
    with pytest.raises(ValueError, match="time unit"):
        build_day(
            DaySpec(kind="short_meal", meal_minutes=25), dt.date(2026, 3, 9), "Mon", catalog, params
        )
    early = dataclasses.replace(catalog.scenario("SC-13"), week_ending=dt.date(2026, 2, 21))
    with pytest.raises(ValueError, match="precedes"):
        build_scenario_timecard(early, memos["DM-04"], catalog, params)
    bad = dataclasses.replace(
        catalog,
        filler_jitter=FillerJitter(
            call=(7.0,), meal_after=(params.meal.deadline_hours,), after_meal=(3.0,)
        ),
    )
    with pytest.raises(ValueError, match="meal deadline"):
        _filler_day(random.Random(1), dt.date(2026, 3, 9), "Mon", bad, params)
    with pytest.raises(ValueError, match="meal deadline"):
        generate(bad, memos, params)


def test_default_work_day_label_matches_catalog(catalog):
    from payroll_triage.evals.expectations import DEFAULT_WORK_DAY_TYPE

    assert DEFAULT_WORK_DAY_TYPE == catalog.labels["day_type"]["work"]
