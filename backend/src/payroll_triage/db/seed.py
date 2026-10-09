"""Seed the database from the committed generated data (`uv run ptc seed`)."""

from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from payroll_triage.corpus.deal_memos import DealMemo, load_deal_memos, parse_deal_memo
from payroll_triage.data.generator import FILLER_MEMOS_FILE, load_generated_timecards
from payroll_triage.paths import generated_dir
from payroll_triage.timecards import Timecard

RESET_TABLES = (
    "audit_log",
    "escalations",
    "return_messages",
    "premium_lines",
    "decisions",
    "suggestions",
    "cases",
    "timecard_days",
    "timecards",
    "deal_memos",
    "employees",
    "productions",
)


def all_deal_memos() -> dict[str, DealMemo]:
    memos = load_deal_memos()
    path = generated_dir() / FILLER_MEMOS_FILE
    with path.open(encoding="utf-8") as fh:
        for raw in json.load(fh)["deal_memos"]:
            memos[raw["id"]] = parse_deal_memo(raw)
    return memos


def seed(pool: ConnectionPool, *, reset: bool = False) -> dict[str, int]:
    memos = all_deal_memos()
    timecards = load_generated_timecards()
    with pool.connection() as conn, conn.transaction():
        if reset:
            # Demo reset only: the audit log is append-only; erasing it is an explicit,
            # transaction-scoped exception that the API and the graph never take.
            conn.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_truncate")
            conn.execute("TRUNCATE " + ", ".join(RESET_TABLES) + " RESTART IDENTITY CASCADE")
            conn.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_truncate")
            for table in ("checkpoints", "checkpoint_writes", "checkpoint_blobs"):
                conn.execute(f"DELETE FROM {table}")
        for memo in memos.values():
            _upsert_memo(conn, memo)
        for tc in timecards:
            _upsert_timecard(conn, tc)
    return {"deal_memos": len(memos), "timecards": len(timecards)}


def _upsert_memo(conn, memo: DealMemo) -> None:
    conn.execute(
        "INSERT INTO productions (id, title, season, employer) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, season = EXCLUDED.season, "
        "employer = EXCLUDED.employer",
        (memo.production_id, memo.production_title, memo.season, memo.employer),
    )
    conn.execute(
        "INSERT INTO employees (id, name) VALUES (%s, %s) "
        "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name",
        (memo.employee_id, memo.employee_name),
    )
    raw: dict[str, Any] = memo.to_dict()
    conn.execute(
        """
        INSERT INTO deal_memos (id, employee_id, production_id, occupation_code, occupation_title,
            guild, hourly_rate_usd, scale_relationship, department, hire_state, work_state,
            start_date, eligibility_status, eligibility_completed_on, raw)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET raw = EXCLUDED.raw,
            hourly_rate_usd = EXCLUDED.hourly_rate_usd,
            scale_relationship = EXCLUDED.scale_relationship,
            eligibility_status = EXCLUDED.eligibility_status,
            eligibility_completed_on = EXCLUDED.eligibility_completed_on
        """,
        (
            memo.id,
            memo.employee_id,
            memo.production_id,
            memo.occupation_code,
            memo.occupation_title,
            memo.guild,
            memo.hourly_rate_usd,
            memo.scale_relationship,
            memo.department,
            memo.hire_state,
            memo.work_state,
            memo.start_date,
            memo.eligibility_status,
            memo.eligibility_completed_on,
            Jsonb(raw),
        ),
    )


def _upsert_timecard(conn, tc: Timecard) -> None:
    conn.execute(
        """
        INSERT INTO timecards (id, scenario_id, employee_id, deal_memo_id, occupation_code,
            department, week_ending, producer_week, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (
            tc.id,
            tc.scenario_id,
            tc.employee_id,
            tc.deal_memo_id,
            tc.occupation_code,
            tc.department,
            tc.week_ending,
            tc.producer_week,
            tc.status,
        ),
    )
    for d in tc.days:
        conn.execute(
            """
            INSERT INTO timecard_days (timecard_id, date, weekday, day_type, work_location,
                call, meal_out, meal_in, wrap)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (timecard_id, date) DO NOTHING
            """,
            (
                tc.id,
                d.date,
                d.weekday,
                d.day_type,
                d.work_location,
                d.call,
                d.meal_out,
                d.meal_in,
                d.wrap,
            ),
        )
