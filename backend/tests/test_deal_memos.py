"""Tests for deal memos (P1.I1.S4)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from payroll_triage.corpus.deal_memos import (
    DealMemoError,
    actual_scale_relationship,
    check_deal_memos,
    load_deal_memos,
    parse_deal_memo,
    scale_shortfall,
)
from payroll_triage.params import load_parameters

EXPECTED_IDS = ["DM-01", "DM-02", "DM-03", "DM-04", "DM-05", "DM-06"]


@pytest.fixture(scope="module")
def params():
    return load_parameters()


@pytest.fixture(scope="module")
def memos():
    return load_deal_memos()


def test_six_memos_with_all_fields(memos):
    assert list(memos) == EXPECTED_IDS
    for memo in memos.values():
        assert memo.employee_name and memo.occupation_code and memo.department
        assert memo.hire_state and memo.work_state and memo.start_date
        assert memo.guild.startswith("Crew Guild")


def test_declared_scale_relationship_matches_schedule_a(memos, params):
    assert check_deal_memos(memos, params) == []
    for memo in memos.values():
        assert actual_scale_relationship(memo, params) == memo.scale_relationship


def test_only_dm04_is_below_scale(memos, params):
    below = [m.id for m in memos.values() if actual_scale_relationship(m, params) == "below"]
    assert below == ["DM-04"]
    shortfall = scale_shortfall(memos["DM-04"], params)
    assert shortfall == params.scale_for("6305").hourly_scale_usd - memos["DM-04"].hourly_rate_usd
    assert shortfall > 0
    for mid in ("DM-01", "DM-02", "DM-03", "DM-05", "DM-06"):
        assert scale_shortfall(memos[mid], params) == Decimal("0.00")


def test_at_scale_memos_equal_schedule_a_exactly(memos, params):
    at = [m for m in memos.values() if m.scale_relationship == "at"]
    assert {m.id for m in at} == {"DM-02", "DM-05", "DM-06"}
    for memo in at:
        assert memo.hourly_rate_usd == params.scale_for(memo.occupation_code).hourly_scale_usd


def test_dm05_eligibility_not_completed(memos):
    assert memos["DM-05"].eligibility_status == "pending"
    assert memos["DM-05"].eligibility_completed_on is None
    for mid in EXPECTED_IDS:
        if mid != "DM-05":
            assert memos[mid].eligibility_status == "completed"
            assert memos[mid].eligibility_completed_on >= memos[mid].start_date


def test_dm04_hire_state_differs_from_work_state(memos):
    assert memos["DM-04"].hire_state != memos["DM-04"].work_state
    for mid in EXPECTED_IDS:
        if mid != "DM-04":
            assert memos[mid].hire_state == memos[mid].work_state


def test_dm02_has_kit_rental(memos):
    kit = [a for a in memos["DM-02"].allowances if a.type == "kit_rental"]
    assert len(kit) == 1 and kit[0].period == "week" and kit[0].amount_usd > 0
    for mid in EXPECTED_IDS:
        if mid != "DM-02":
            assert memos[mid].allowances == ()


def test_start_dates_within_agreement_effective_period(memos, params):
    for memo in memos.values():
        assert params.agreement.in_force_on(memo.start_date)


def test_parse_rejects_inconsistent_eligibility(memos):
    raw = memos["DM-01"].to_dict()
    raw["eligibility_verification"] = {"status": "completed", "completed_on": None}
    with pytest.raises(DealMemoError):
        parse_deal_memo(raw)
    raw["eligibility_verification"] = {"status": "pending", "completed_on": "2026-01-13"}
    with pytest.raises(DealMemoError):
        parse_deal_memo(raw)


def test_check_detects_wrong_declaration(memos, params):
    raw = memos["DM-01"].to_dict()
    raw["scale_relationship"] = "at"
    memo = parse_deal_memo(raw)
    problems = check_deal_memos({memo.id: memo}, params)
    assert problems and "declares at scale" in problems[0]


def test_round_trip_to_dict(memos):
    for memo in memos.values():
        again = parse_deal_memo(memo.to_dict())
        assert again == memo


def test_dates_are_dates(memos):
    assert isinstance(memos["DM-01"].start_date, dt.date)
