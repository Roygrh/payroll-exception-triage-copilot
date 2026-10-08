"""Tests for the rule parameters loader (P1.I1.S2).

The design values asserted here mirror docs/requirements/domain-model.md,
sections 1 to 4. They are the one place where numbers are written twice on purpose:
if the YAML drifts from the agreed design, this suite fails.
"""

from __future__ import annotations

import copy
import datetime as dt
from decimal import Decimal

import pytest

from payroll_triage.params import (
    ParameterError,
    load_parameters,
    load_raw,
    load_schema,
    parse_parameters,
)


@pytest.fixture(scope="module")
def raw():
    return load_raw()


@pytest.fixture(scope="module")
def schema():
    return load_schema()


@pytest.fixture(scope="module")
def params():
    return load_parameters()


def test_yaml_validates_against_schema(raw, schema):
    parse_parameters(raw, schema)


def test_design_values_match_domain_model(params):
    assert params.agreement.code == "CGMA"
    assert params.agreement.version == "2026.1"
    assert params.agreement.effective_from == dt.date(2026, 1, 1)
    assert params.agreement.effective_to == dt.date(2026, 12, 31)
    assert params.agreement.citation_prefix == "CGMA-2026.1"
    assert params.meal.deadline_hours == 6.0
    assert params.meal.min_duration_minutes == 30
    assert params.meal.penalty_increment_minutes == 30
    assert params.meal.penalty_schedule_usd == (Decimal("8.25"), Decimal("11.00"), Decimal("13.75"))
    assert params.extended_day.threshold_hours == 12.0
    assert params.extended_day.multiplier == 2.0
    assert params.rest.min_hours == 10.0
    assert params.rest.invasion_multiplier == 2.0
    assert params.eligibility.deadline_business_days == 3
    assert params.overtime.daily_after_hours == 8.0
    assert params.overtime.daily_multiplier == 1.5
    assert params.overtime.weekly_after_hours == 40.0
    assert params.overtime.weekly_multiplier == 1.5


def test_schedule_a_matches_domain_model(params):
    expected = {
        "4110": ("CAMERA OPERATOR", Decimal("58.40")),
        "4125": ("CAMERA ASSISTANT", Decimal("44.10")),
        "5210": ("PRODUCTION COORDINATOR", Decimal("39.75")),
        "6305": ("PROPERTY ASSISTANT", Decimal("36.20")),
        "7020": ("SET DISPATCHER", Decimal("33.90")),
    }
    actual = {e.code: (e.occupation, e.hourly_scale_usd) for e in params.schedule_a}
    assert actual == expected


def test_rule_sections_match_domain_model(params):
    expected = {
        "MEAL_PERIOD": "8.2",
        "EXTENDED_DAY": "6.2",
        "REST_PERIOD": "9.1",
        "TIME_ENTRY_COMPLETENESS": "7.4",
        "SCALE_RATE": "5.1",
        "ELIGIBILITY_DOC": "14.2",
    }
    assert {rid: ref.section for rid, ref in params.rules.items()} == expected
    assert params.citation_key("8.2") == "CGMA-2026.1-8.2"


def test_scale_lookup(params):
    assert params.scale_for("6305").hourly_scale_usd == Decimal("36.20")
    with pytest.raises(ParameterError):
        params.scale_for("0000")


@pytest.mark.parametrize(
    "path",
    [
        ("meal", "deadline_hours"),
        ("meal", "penalty_schedule_usd"),
        ("extended_day", "threshold_hours"),
        ("rest", "min_hours"),
        ("eligibility", "deadline_business_days"),
        ("rules", "MEAL_PERIOD"),
        ("schedule_a",),
    ],
)
def test_missing_value_is_rejected(raw, schema, path):
    broken = copy.deepcopy(raw)
    node = broken
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    with pytest.raises(ParameterError):
        parse_parameters(broken, schema)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("meal", "deadline_hours"), 2.0),
        (("meal", "deadline_hours"), 9.0),
        (("meal", "min_duration_minutes"), 5),
        (("meal", "penalty_schedule_usd"), []),
        (("meal", "penalty_schedule_usd"), [7.5, -1]),
        (("extended_day", "threshold_hours"), 9.0),
        (("rest", "min_hours"), 20.0),
        (("eligibility", "deadline_business_days"), 0),
        (("overtime", "weekly_after_hours"), 100.0),
        (("agreement", "version"), "v1"),
    ],
)
def test_out_of_range_value_is_rejected(raw, schema, path, value):
    broken = copy.deepcopy(raw)
    node = broken
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(ParameterError):
        parse_parameters(broken, schema)


def test_unknown_key_is_rejected(raw, schema):
    broken = copy.deepcopy(raw)
    broken["meal"]["grace_minutes"] = 5
    with pytest.raises(ParameterError):
        parse_parameters(broken, schema)


def test_semantic_check_citation_prefix(raw, schema):
    broken = copy.deepcopy(raw)
    broken["agreement"]["citation_prefix"] = "CGMA-2025.9"
    with pytest.raises(ParameterError, match="citation_prefix"):
        parse_parameters(broken, schema)


def test_semantic_check_time_unit_multiple(raw, schema):
    broken = copy.deepcopy(raw)
    broken["meal"]["deadline_hours"] = 6.25
    with pytest.raises(ParameterError, match="time_unit_hours"):
        parse_parameters(broken, schema)


def test_semantic_check_duplicate_code(raw, schema):
    broken = copy.deepcopy(raw)
    broken["schedule_a"].append(dict(broken["schedule_a"][0]))
    with pytest.raises(ParameterError, match="duplicate"):
        parse_parameters(broken, schema)
