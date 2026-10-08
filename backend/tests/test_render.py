"""Tests for the agreement renderer (P1.I1.S3)."""

from __future__ import annotations

import re

import pytest

from payroll_triage.corpus.render import (
    agreement_output_path,
    check_agreement,
    citation_keys_in,
    render_agreement,
    word_count,
)
from payroll_triage.params import load_parameters

PAGE_WORDS_LOW = 15 * 400  # 15 pages at roughly 400 words per page
PAGE_WORDS_HIGH = 20 * 450

OUTLINE_SECTIONS = [
    "1.2",
    "2.2",
    "3.2",
    "4.1",
    "5.1",
    "6.1",
    "6.2",
    "6.3",
    "7.4",
    "8.2",
    "8.3",
    "9.1",
    "9.2",
    "10.1",
    "11.2",
    "12.1",
    "13.2",
    "14.2",
    "SCH-A",
    "SCH-B",
]


@pytest.fixture(scope="module")
def params():
    return load_parameters()


@pytest.fixture(scope="module")
def rendered(params):
    return render_agreement(params)


def test_committed_file_is_current(params):
    assert check_agreement(params) == [], "run `uv run ptc render-agreement` and commit the result"


def test_render_is_deterministic(params):
    assert render_agreement(params) == render_agreement(params)


def test_length_is_fifteen_to_twenty_pages(rendered):
    n = word_count(rendered)
    assert PAGE_WORDS_LOW <= n <= PAGE_WORDS_HIGH, f"word count {n}"


def test_outline_sections_present(params, rendered):
    keys = citation_keys_in(rendered)
    for section in OUTLINE_SECTIONS:
        assert params.citation_key(section) in keys, section
    assert len(keys) == len(set(keys)), "citation keys must be unique"


def test_rule_sections_present_with_titles(params, rendered):
    for ref in params.rules.values():
        key = params.citation_key(ref.section)
        pattern = re.compile(
            rf"^### {re.escape(ref.section)} (?P<title>.+) \[{re.escape(key)}\]$", re.M
        )
        m = pattern.search(rendered)
        assert m, f"missing heading for {ref.rule_id} ({key})"
        assert m.group("title").lower() == ref.title.lower(), ref.rule_id


def test_numbers_come_from_parameters(params, rendered):
    m = params.meal
    assert f"not later than {m.deadline_hours:.1f} hours after Call" in rendered
    assert f"not less than {m.min_duration_minutes} minutes" in rendered
    assert f"increments of {m.penalty_increment_minutes} minutes" in rendered
    for amount in m.penalty_schedule_usd:
        assert f"| {amount:.2f} |" in rendered
    assert (
        f"in excess of {params.extended_day.threshold_hours:.1f} hours on a single Workday"
        in rendered
    )
    assert f"{params.extended_day.multiplier:.1f} times" in rendered
    assert f"not less than {params.rest.min_hours:.1f} hours between Wrap" in rendered
    assert f"{params.rest.invasion_multiplier:.1f} times the hourly rate" in rendered
    assert f"within {params.eligibility.deadline_business_days} business days" in rendered
    assert f"in excess of {params.overtime.daily_after_hours:.1f} hours on a Workday" in rendered
    assert (
        f"in excess of {params.overtime.weekly_after_hours:.1f} hours in a Payroll Week" in rendered
    )
    for entry in params.schedule_a:
        assert f"| {entry.code} | {entry.occupation} | {entry.hourly_scale_usd:.2f} |" in rendered


def test_changing_a_parameter_changes_the_text(params, rendered, tmp_path):
    import copy

    from payroll_triage.params import load_raw, load_schema, parse_parameters

    raw = copy.deepcopy(load_raw())
    raw["meal"]["deadline_hours"] = 5.5
    other = parse_parameters(raw, load_schema())
    assert "not later than 5.5 hours after Call" in render_agreement(other)
    assert "not later than 5.5 hours after Call" not in rendered


def test_synthetic_notice_and_metadata(params, rendered):
    assert "Synthetic document" in rendered
    assert params.agreement.effective_from.isoformat() in rendered
    assert params.agreement.effective_to.isoformat() in rendered
    assert agreement_output_path(params).name == "cgma-2026.1.md"


def test_no_em_dash(rendered):
    from payroll_triage.paths import templates_dir

    assert chr(0x2014) not in rendered
    template_text = (templates_dir() / "cgma.md.j2").read_text(encoding="utf-8")
    assert chr(0x2014) not in template_text


def test_related_sections_resolve_to_headings(params, rendered):
    keys = set(citation_keys_in(rendered))
    for ref in params.rules.values():
        for section in ref.related_sections:
            assert params.citation_key(section) in keys, f"{ref.rule_id}: {section}"


def test_rendered_text_is_lf_and_ends_with_single_newline(rendered):
    assert "\r" not in rendered
    assert rendered.endswith("\n") and not rendered.endswith("\n\n")


def test_citation_keys_only_from_headings():
    body = (
        "## 8.2 Title [CGMA-2026.1-8.2]\ntext mentions [CGMA-2026.1-9.9] inline\n### No key here\n"
    )
    assert citation_keys_in(body) == ["CGMA-2026.1-8.2"]


def test_undefined_variable_fails_loudly(params, tmp_path):
    from jinja2 import UndefinedError

    (tmp_path / "cgma.md.j2").write_text("{{ meal.no_such_value }}", encoding="utf-8")
    with pytest.raises(UndefinedError):
        render_agreement(params, template_dir=tmp_path)


def test_write_agreement_writes_lf(params, tmp_path, monkeypatch):
    import payroll_triage.corpus.render as render_mod

    monkeypatch.setattr(render_mod, "corpus_dir", lambda: tmp_path)
    out = render_mod.write_agreement(params)
    raw = out.read_bytes()
    assert out.name == "cgma-2026.1.md"
    assert b"\r\n" not in raw
    assert render_mod.check_agreement(params) == []


def test_hours_filter_is_lossless():
    from payroll_triage.corpus.render import _fmt_hours, _fmt_multiplier

    assert _fmt_hours(6.0) == "6.0"
    assert _fmt_hours(6.25) == "6.25"
    assert _fmt_multiplier(1.5) == "1.5"
    assert _fmt_multiplier(2) == "2.0"


def test_ordinal_raises_beyond_table():
    from payroll_triage.corpus.render import _ORDINALS, _ordinal

    assert _ordinal(1) == "First"
    with pytest.raises(ValueError):
        _ordinal(len(_ORDINALS) + 1)
