"""Chunker, citation validator and the ranking rule (no database, no model)."""

from __future__ import annotations

import pytest

from payroll_triage.corpus.deal_memos import load_deal_memos
from payroll_triage.corpus.render import citation_keys_in, render_agreement
from payroll_triage.params import load_parameters
from payroll_triage.retrieval.chunker import (
    build_corpus,
    chunk_agreement,
    chunk_deal_memo,
    is_deal_memo_key,
)
from payroll_triage.retrieval.citations import validate_citations
from payroll_triage.retrieval.search import RRF_K, combine, fuse_rankings


@pytest.fixture(scope="module")
def params():
    return load_parameters()


@pytest.fixture(scope="module")
def memos():
    return load_deal_memos()


@pytest.fixture(scope="module")
def corpus(params, memos):
    return build_corpus(params, memos, render_agreement(params))


def test_every_heading_becomes_one_chunk_with_its_key(params, corpus):
    text = render_agreement(params)
    keys = citation_keys_in(text)
    agreement = [c for c in corpus if c.source_type == "agreement"]
    assert [c.citation_key for c in agreement] == keys
    assert len(keys) >= 90 and len(agreement) == len(keys)
    by_key = {c.citation_key: c for c in agreement}
    meal = by_key[params.citation_key(params.rule("MEAL_PERIOD").section)]
    assert meal.section == "8.2" and meal.version == params.agreement.version
    assert "first Meal Period" in meal.body and str(params.meal.deadline_hours) in meal.body
    assert by_key[params.citation_key("SCH-B")].section == "SCH-B"
    assert by_key[params.citation_key("SCH-B")].body.count("|") > 6


def test_deal_memo_chunk_uses_the_memo_values(params, memos):
    chunk = chunk_deal_memo(memos["DM-01"], params)
    assert chunk.citation_key == "DM-01" and chunk.source_type == "deal_memo"
    assert f"{memos['DM-01'].hourly_rate_usd:.2f}" in chunk.body
    assert memos["DM-01"].employee_name in chunk.heading
    assert is_deal_memo_key("DM-01") and not is_deal_memo_key("CGMA-2026.1-8.2")


def test_chunker_rejects_foreign_prefix(params):
    with pytest.raises(ValueError, match="prefix"):
        chunk_agreement("### 1.1 X [OTHER-2026.1-1.1]\n\nbody\n", params)


def test_citation_validation_rules(params, corpus):
    lookup = {c.citation_key: c for c in corpus}.get
    v = params.agreement.version
    good = validate_citations(
        ["CGMA-2026.1-8.2", "DM-01"], lookup, version_in_force=v, deal_memo_id="DM-01"
    )
    assert good.valid and all(c.status == "valid" for c in good.checks)

    unknown = validate_citations(
        ["CGMA-2026.1-99.9"], lookup, version_in_force=v, deal_memo_id="DM-01"
    )
    assert not unknown.valid and unknown.checks[0].status == "unknown_key"

    other_memo = validate_citations(["DM-02"], lookup, version_in_force=v, deal_memo_id="DM-01")
    assert not other_memo.valid and other_memo.checks[0].status == "wrong_deal_memo"

    wrong_version = validate_citations(
        ["CGMA-2026.1-8.2"], lookup, version_in_force="2027.1", deal_memo_id="DM-01"
    )
    assert not wrong_version.valid and wrong_version.checks[0].status == "wrong_version"

    missing = validate_citations(
        ["CGMA-2026.1-8.3"],
        lookup,
        version_in_force=v,
        deal_memo_id="DM-01",
        required_keys=["CGMA-2026.1-8.2"],
    )
    assert not missing.valid and missing.required_missing == ("CGMA-2026.1-8.2",)

    empty = validate_citations([], lookup, version_in_force=v, deal_memo_id="DM-01")
    assert not empty.valid


def test_reciprocal_rank_fusion_rule():
    fused = fuse_rankings([["a", "b", "c"], ["b", "a", "d"]])
    scores = dict(fused)
    assert scores["a"] == pytest.approx(1 / (RRF_K + 1) + 1 / (RRF_K + 2))
    assert scores["b"] == pytest.approx(1 / (RRF_K + 2) + 1 / (RRF_K + 1))
    assert scores["c"] == pytest.approx(1 / (RRF_K + 3))
    assert [k for k, _ in fused][:2] == ["a", "b"]  # tie broken by key
    assert fused[-1][0] == "d" or fused[-1][0] == "c"


def test_combine_keeps_ranks_and_truncates(corpus):
    by_key = {c.citation_key: c for c in corpus}
    v = [by_key["CGMA-2026.1-8.2"], by_key["CGMA-2026.1-8.3"]]
    t = [by_key["CGMA-2026.1-8.3"], by_key["DM-01"]]
    ranked = combine(v, t, top_k=2)
    assert [r.chunk.citation_key for r in ranked] == ["CGMA-2026.1-8.3", "CGMA-2026.1-8.2"]
    assert ranked[0].vector_rank == 2 and ranked[0].text_rank == 1
    assert ranked[1].text_rank is None
