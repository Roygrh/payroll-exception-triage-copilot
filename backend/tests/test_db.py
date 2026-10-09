"""Integration tests against PostgreSQL 16 with pgvector (database `ptc_test`, created on demand).

Requires the compose database (docker compose -f deployment/docker-compose.yml up db). The
tests are skipped only when no server answers on DATABASE_URL; the skip reason is printed.
The module fixture drops and recreates the schema, so concurrent processes are serialized
with a PostgreSQL advisory lock held for the duration of the module.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import psycopg
import pytest
from langgraph.checkpoint.postgres import PostgresSaver

from payroll_triage.config import get_settings
from payroll_triage.corpus.deal_memos import load_deal_memos
from payroll_triage.corpus.render import citation_keys_in, render_agreement
from payroll_triage.db.connection import app_pool, checkpointer_pool
from payroll_triage.db.migrate import apply_migrations, migration_files
from payroll_triage.db.seed import all_deal_memos, seed
from payroll_triage.db.store import CaseRecord, ExecutionPlan, PostgresCaseStore, PremiumLine
from payroll_triage.graph.build import build_graph
from payroll_triage.graph.nodes import Deps, retrieval_query
from payroll_triage.graph.service import TriageService
from payroll_triage.params import load_parameters
from payroll_triage.retrieval.chunker import build_corpus
from payroll_triage.retrieval.index import ingest_corpus
from payroll_triage.retrieval.search import PostgresRetriever
from payroll_triage.runtime import demo_clock
from tests.support.fake_adapter import FakeAdapter, good_outputs

TEST_DB = "ptc_test"
LOCK_KEY = 20261008  # advisory lock key shared by every process using ptc_test


def _test_url() -> str | None:
    url = get_settings().database_url
    base, _, _name = url.rpartition("/")
    admin = base + "/postgres"
    try:
        with psycopg.connect(admin, autocommit=True, connect_timeout=3) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)
            ).fetchone()
            if not exists:
                conn.execute(f"CREATE DATABASE {TEST_DB}")
    except psycopg.OperationalError as exc:
        pytest.skip(f"no PostgreSQL server for integration tests: {exc}")
    return base + "/" + TEST_DB


@pytest.fixture(scope="module")
def url():
    url = _test_url()
    # Serialize concurrent pytest processes on the shared test database: the lock is held by
    # this connection until the module finishes.
    guard = psycopg.connect(url, autocommit=True)
    guard.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    applied = apply_migrations(url)
    assert applied == [p.name.split("_")[0] for p in migration_files()]
    assert apply_migrations(url) == []  # idempotent
    with PostgresSaver.from_conn_string(url) as saver:
        saver.setup()
    yield url
    guard.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    guard.close()


@pytest.fixture(scope="module")
def pool(url):
    pool = app_pool(url)
    yield pool
    pool.close()


@pytest.fixture(scope="module")
def store(pool):
    seed(pool, reset=True)
    return PostgresCaseStore(pool)


@pytest.fixture(scope="module")
def params():
    return load_parameters()


@pytest.fixture(scope="module")
def embedder():
    from payroll_triage.retrieval.embeddings import FastEmbedEmbedder

    return FastEmbedEmbedder()


@pytest.fixture(scope="module")
def retriever(pool, params, embedder):
    memos = all_deal_memos()
    count = ingest_corpus(pool, params, memos, embedder)
    assert count == len(citation_keys_in(render_agreement(params))) + len(memos)
    return PostgresRetriever(pool, embedder)


def test_migration_creates_all_tables_including_checkpoints(url):
    with psycopg.connect(url) as conn:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
        }
    expected = {
        "agreement_versions",
        "corpus_chunks",
        "productions",
        "employees",
        "deal_memos",
        "timecards",
        "timecard_days",
        "cases",
        "suggestions",
        "decisions",
        "premium_lines",
        "return_messages",
        "escalations",
        "audit_log",
        "schema_migrations",
        "checkpoints",
        "checkpoint_writes",
        "checkpoint_blobs",
    }
    assert expected <= names


def test_seed_round_trips_timecards_and_memos(store):
    tc = store.get_timecard("TC-EMP-1001-20260314")
    assert tc is not None and tc.scenario_id == "SC-03" and tc.employee_name
    assert len(tc.days) == 5 and tc.days[1].meal_out == 13.5
    memo = store.get_deal_memo("DM-01")
    assert memo == load_deal_memos()["DM-01"].__class__(
        **{**load_deal_memos()["DM-01"].__dict__, "source_path": None}
    )
    week = store.list_timecards(dt.date(2026, 3, 14), "Ready for approver 1")
    assert len(week) == 10  # six showcase scenarios plus four filler crew


def test_audit_log_is_append_only_at_the_database(store, pool):
    case = CaseRecord(
        id="CASE-AUDIT-TEST",
        timecard_id="TC-EMP-1001-20260221",
        deal_memo_id="DM-01",
        week_ending=dt.date(2026, 2, 21),
        findings=[],
        policy_action="approve",
        amount_usd=Decimal("0.00"),
        priority_score=1,
        status="detected",
    )
    store.create_case(case)
    entry = store.add_audit(case.id, "review", "system", {"reason": "test"})
    with pool.connection() as conn:
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            conn.execute("UPDATE audit_log SET actor = 'x' WHERE id = %s", (entry,))
    with pool.connection() as conn:
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            conn.execute("DELETE FROM audit_log WHERE id = %s", (entry,))
    assert store.list_audit(case.id)[0]["actor"] == "system"


def test_execution_plan_is_atomic(store, pool, params):
    plan = ExecutionPlan(
        case_id="CASE-AUDIT-TEST",
        timecard_id="TC-EMP-1001-20260221",
        action="approve",
        actor="tester",
        timecard_status_after="Ready for approver 2",
        case_status_after="approved",
        decision_message=None,
        premium_lines=(
            PremiumLine(
                "MEAL_PERIOD",
                dt.date(2026, 2, 17),
                "test line",
                params.meal.penalty_schedule_usd[0],
            ),
        ),
    )
    effects = store.apply_execution(plan)
    assert effects["premium_total_usd"] == f"{params.meal.penalty_schedule_usd[0]:.2f}"
    assert effects["case_status"] == "approved" and effects["decision_id"] >= 1
    assert store.get_timecard("TC-EMP-1001-20260221").status == "Ready for approver 2"
    bad = ExecutionPlan(**{**plan.__dict__, "case_status_after": "not-a-status"})
    with pytest.raises(psycopg.errors.CheckViolation):
        store.apply_execution(bad)
    with pool.connection() as conn:
        count = conn.execute("SELECT count(*) FROM premium_lines").fetchone()[0]
        decisions = conn.execute("SELECT count(*) FROM decisions").fetchone()[0]
    assert count == 1 and decisions == 1  # the failed plan wrote nothing, not even its decision
    with pool.connection() as conn:
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            conn.execute("TRUNCATE audit_log")


def test_hybrid_search_returns_section_8_2_and_the_deal_memo(retriever, params):
    key = params.citation_key(params.rule("MEAL_PERIOD").section)
    finding = {"rule_id": "MEAL_PERIOD", "facts": {"is_late": True, "is_short": False}}
    ranked = retriever.search(retrieval_query(finding, params), top_k=6)
    keys = [r.chunk.citation_key for r in ranked]
    assert key in keys[:3], keys
    assert params.citation_key("SCH-B") in keys, keys
    assert all(r.vector_rank or r.text_rank for r in ranked)
    memo = retriever.search("deal memo Avery Lindqvist camera operator hourly rate", top_k=6)
    assert "DM-01" in [r.chunk.citation_key for r in memo][:3]
    assert retriever.get(key).version == params.agreement.version
    assert retriever.get("DM-01").source_type == "deal_memo"
    assert retriever.get("CGMA-2026.1-99.9") is None


def test_graph_checkpoint_survives_a_rebuild(url, pool, store, retriever, params):
    """Pause with one graph instance, resume with a new one built on the same database."""
    saver_pool = checkpointer_pool(url)
    try:
        adapter = FakeAdapter(good_outputs("CGMA-2026.1-8.2", "DM-01", "approve"))
        deps = Deps(
            store=store, retriever=retriever, adapter=adapter, params=params, clock=demo_clock()
        )
        first = TriageService(build_graph(deps, PostgresSaver(saver_pool)), deps)
        result = first.run_timecard("TC-EMP-1001-20260314")
        assert result["status"] == "awaiting_decision" and result["waiting_on"] == [
            "human_checkpoint"
        ]
        case_id = result["case_id"]

        second = TriageService(build_graph(deps, PostgresSaver(saver_pool)), deps)
        detail = second.case_detail(case_id)
        assert detail["waiting_on"] == ["human_checkpoint"]
        assert detail["checkpoint_id"] == result["checkpoint_id"]
        outcome = second.decide(case_id, {"action": "approve", "actor": "sam.verhoeven"})
        assert outcome["status"] == "approved"
        assert outcome["checkpoint_id_before"] == result["checkpoint_id"]
        assert outcome["checkpoint_id_after"] != result["checkpoint_id"]
        kinds = [a["entry_kind"] for a in store.list_audit(case_id)]
        assert kinds == [
            "suggestion",
            "suggestion",
            "suggestion",
            "validation",
            "decision",
            "execution",
        ]
        assert store.get_timecard("TC-EMP-1001-20260314").status == "Ready for approver 2"
        assert store.list_queue() == []
    finally:
        saver_pool.close()


def test_corpus_chunks_match_the_pure_chunker(retriever, params):
    memos = all_deal_memos()
    chunks = build_corpus(params, memos, render_agreement(params))
    for chunk in chunks[:5] + chunks[-2:]:
        stored = retriever.get(chunk.citation_key)
        assert stored is not None and stored.body == chunk.body and stored.heading == chunk.heading
