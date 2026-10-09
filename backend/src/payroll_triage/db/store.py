"""Case store: the only write path to application tables.

Every write method is called by code (graph nodes or the API), never by the
LLM adapter. Decisions and their effects are written only by `apply_execution`
(one transaction), which the execute node calls after the human checkpoint
with the human's identity as actor (ADR-009). The audit log is append-only at
the database level (trigger in migration 0001).
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from payroll_triage.corpus.deal_memos import DealMemo, parse_deal_memo
from payroll_triage.timecards import Timecard, TimecardDay

CASE_STATUSES = (
    "detected",
    "awaiting_decision",
    "needs_human_review",
    "approved",
    "returned",
    "escalated",
)
OPEN_STATUSES = ("awaiting_decision", "needs_human_review")


def case_id_for(timecard_id: str) -> str:
    return "CASE-" + timecard_id.removeprefix("TC-")


@dataclass(frozen=True)
class CaseRecord:
    id: str
    timecard_id: str
    deal_memo_id: str
    week_ending: dt.date
    findings: list[dict[str, Any]]
    policy_action: str
    amount_usd: Decimal
    priority_score: int
    status: str
    review_reason: str | None = None
    thread_id: str = ""
    created_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timecard_id": self.timecard_id,
            "deal_memo_id": self.deal_memo_id,
            "week_ending": self.week_ending.isoformat(),
            "findings": self.findings,
            "policy_action": self.policy_action,
            "amount_usd": f"{self.amount_usd:.2f}",
            "priority_score": self.priority_score,
            "status": self.status,
            "review_reason": self.review_reason,
            "thread_id": self.thread_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass(frozen=True)
class PremiumLine:
    rule_id: str
    day_date: dt.date | None
    description: str
    amount_usd: Decimal


@dataclass(frozen=True)
class ExecutionPlan:
    """What `apply_execution` will write, computed by code from the human decision."""

    case_id: str
    timecard_id: str
    action: str
    actor: str
    timecard_status_after: str | None
    case_status_after: str
    premium_lines: tuple[PremiumLine, ...] = ()
    return_message: str | None = None
    recipient_role: str | None = None
    escalation_note: str | None = None
    escalation_note_source: str | None = None  # "human" | "default"
    decision_message: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class CaseStore(Protocol):
    def get_timecard(self, timecard_id: str) -> Timecard | None: ...
    def get_deal_memo(self, memo_id: str) -> DealMemo | None: ...
    def list_timecards(self, week_ending: dt.date, status: str) -> list[Timecard]: ...
    def get_case(self, case_id: str) -> CaseRecord | None: ...
    def get_case_by_timecard(self, timecard_id: str) -> CaseRecord | None: ...
    def list_queue(self) -> list[CaseRecord]: ...
    def create_case(self, case: CaseRecord) -> None: ...
    def set_case_status(self, case_id: str, status: str, review_reason: str | None) -> None: ...
    def add_suggestion(
        self,
        case_id: str,
        kind: str,
        content: dict[str, Any],
        provider: str,
        model: str,
        adapter_version: str,
    ) -> int: ...
    def set_suggestion_validation(
        self, suggestion_id: int, status: str, detail: dict[str, Any]
    ) -> None: ...
    def list_suggestions(self, case_id: str) -> list[dict[str, Any]]: ...
    def add_audit(
        self, case_id: str, entry_kind: str, actor: str, payload: dict[str, Any]
    ) -> int: ...
    def list_audit(self, case_id: str) -> list[dict[str, Any]]: ...
    def apply_execution(self, plan: ExecutionPlan) -> dict[str, Any]: ...


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


def _jsonb(value: Any) -> Jsonb:
    return Jsonb(_plain(value))


class PostgresCaseStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    # ---------- reads ----------

    def get_timecard(self, timecard_id: str) -> Timecard | None:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(_TIMECARD_SELECT + " WHERE t.id = %s", (timecard_id,)).fetchone()
            if row is None:
                return None
            days = cur.execute(
                "SELECT * FROM timecard_days WHERE timecard_id = %s ORDER BY date", (timecard_id,)
            ).fetchall()
        return _timecard_from_rows(row, days)

    def list_timecards(self, week_ending: dt.date, status: str) -> list[Timecard]:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                _TIMECARD_SELECT + " WHERE t.week_ending = %s AND t.status = %s ORDER BY t.id",
                (week_ending, status),
            ).fetchall()
            out = []
            for row in rows:
                days = cur.execute(
                    "SELECT * FROM timecard_days WHERE timecard_id = %s ORDER BY date",
                    (row["id"],),
                ).fetchall()
                out.append(_timecard_from_rows(row, days))
        return out

    def get_deal_memo(self, memo_id: str) -> DealMemo | None:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute("SELECT raw FROM deal_memos WHERE id = %s", (memo_id,)).fetchone()
        return parse_deal_memo(row["raw"]) if row else None

    def get_case(self, case_id: str) -> CaseRecord | None:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute("SELECT * FROM cases WHERE id = %s", (case_id,)).fetchone()
        return _case_from_row(row) if row else None

    def get_case_by_timecard(self, timecard_id: str) -> CaseRecord | None:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "SELECT * FROM cases WHERE timecard_id = %s", (timecard_id,)
            ).fetchone()
        return _case_from_row(row) if row else None

    def list_queue(self) -> list[CaseRecord]:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                "SELECT * FROM cases WHERE status = ANY(%s) "
                "ORDER BY priority_score DESC, week_ending ASC, id ASC",
                (list(OPEN_STATUSES),),
            ).fetchall()
        return [_case_from_row(r) for r in rows]

    def list_suggestions(self, case_id: str) -> list[dict[str, Any]]:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                "SELECT * FROM suggestions WHERE case_id = %s ORDER BY id", (case_id,)
            ).fetchall()
        return [_plain(dict(r)) for r in rows]

    def list_audit(self, case_id: str) -> list[dict[str, Any]]:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                "SELECT * FROM audit_log WHERE case_id = %s ORDER BY id", (case_id,)
            ).fetchall()
        return [_plain(dict(r)) for r in rows]

    # ---------- writes (code only) ----------

    def create_case(self, case: CaseRecord) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO cases (id, timecard_id, deal_memo_id, week_ending, findings,
                    policy_action, amount_usd, priority_score, status, review_reason, thread_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    case.id,
                    case.timecard_id,
                    case.deal_memo_id,
                    case.week_ending,
                    _jsonb(case.findings),
                    case.policy_action,
                    case.amount_usd,
                    case.priority_score,
                    case.status,
                    case.review_reason,
                    case.thread_id or case.id,
                ),
            )

    def set_case_status(self, case_id: str, status: str, review_reason: str | None) -> None:
        if status not in CASE_STATUSES:
            raise ValueError(f"unknown case status {status!r}")
        with self.pool.connection() as conn:
            conn.execute(
                "UPDATE cases SET status = %s, review_reason = %s, updated_at = now() "
                "WHERE id = %s",
                (status, review_reason, case_id),
            )

    def add_suggestion(
        self,
        case_id: str,
        kind: str,
        content: dict[str, Any],
        provider: str,
        model: str,
        adapter_version: str,
    ) -> int:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO suggestions (case_id, kind, content, provider, model, adapter_version)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (case_id, kind, _jsonb(content), provider, model, adapter_version),
            ).fetchone()
        return int(row[0])  # type: ignore[index]

    def set_suggestion_validation(
        self, suggestion_id: int, status: str, detail: dict[str, Any]
    ) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "UPDATE suggestions SET validation_status = %s, validation_detail = %s "
                "WHERE id = %s",
                (status, _jsonb(detail), suggestion_id),
            )

    def add_audit(self, case_id: str, entry_kind: str, actor: str, payload: dict[str, Any]) -> int:
        with self.pool.connection() as conn:
            row = conn.execute(
                "INSERT INTO audit_log (case_id, entry_kind, actor, payload) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (case_id, entry_kind, actor, _jsonb(payload)),
            ).fetchone()
        return int(row[0])  # type: ignore[index]

    def apply_execution(self, plan: ExecutionPlan) -> dict[str, Any]:
        """Apply the plan in one transaction; nothing is written if any statement fails."""
        effects: dict[str, Any] = {"action": plan.action, "actor": plan.actor}
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                "INSERT INTO decisions (case_id, actor, action, message) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (plan.case_id, plan.actor, plan.action, plan.decision_message),
            ).fetchone()
            effects["decision_id"] = int(row[0])  # type: ignore[index]
            if plan.timecard_status_after:
                conn.execute(
                    "UPDATE timecards SET status = %s WHERE id = %s",
                    (plan.timecard_status_after, plan.timecard_id),
                )
                effects["timecard_status"] = plan.timecard_status_after
            if plan.premium_lines:
                ids = []
                for line in plan.premium_lines:
                    row = conn.execute(
                        """
                        INSERT INTO premium_lines (timecard_id, case_id, rule_id, day_date,
                            description, amount_usd, created_by)
                        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                        """,
                        (
                            plan.timecard_id,
                            plan.case_id,
                            line.rule_id,
                            line.day_date,
                            line.description,
                            line.amount_usd,
                            plan.actor,
                        ),
                    ).fetchone()
                    ids.append(int(row[0]))  # type: ignore[index]
                effects["premium_line_ids"] = ids
                effects["premium_total_usd"] = (
                    f"{sum(line.amount_usd for line in plan.premium_lines):.2f}"
                )
            if plan.return_message is not None:
                row = conn.execute(
                    "INSERT INTO return_messages (case_id, recipient_role, body, sent_by) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    (
                        plan.case_id,
                        plan.recipient_role or "employee",
                        plan.return_message,
                        plan.actor,
                    ),
                ).fetchone()
                effects["return_message_id"] = int(row[0])  # type: ignore[index]
            if plan.escalation_note is not None:
                row = conn.execute(
                    "INSERT INTO escalations (case_id, note, raised_by) VALUES (%s, %s, %s) "
                    "RETURNING id",
                    (plan.case_id, plan.escalation_note, plan.actor),
                ).fetchone()
                effects["escalation_id"] = int(row[0])  # type: ignore[index]
                effects["escalation_note_source"] = plan.escalation_note_source
            conn.execute(
                "UPDATE cases SET status = %s, updated_at = now() WHERE id = %s",
                (plan.case_status_after, plan.case_id),
            )
            effects["case_status"] = plan.case_status_after
        return effects


# ---------- row mapping ----------

_TIMECARD_SELECT = (
    "SELECT t.*, e.name AS employee_name FROM timecards t JOIN employees e ON e.id = t.employee_id"
)


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def _timecard_from_rows(row: dict[str, Any], days: list[dict[str, Any]]) -> Timecard:
    return Timecard(
        id=row["id"],
        scenario_id=row["scenario_id"],
        employee_id=row["employee_id"],
        employee_name=row["employee_name"],
        deal_memo_id=row["deal_memo_id"],
        occupation_code=row["occupation_code"],
        department=row["department"],
        week_ending=row["week_ending"],
        producer_week=row["producer_week"],
        status=row["status"],
        days=tuple(
            TimecardDay(
                date=d["date"],
                weekday=d["weekday"],
                day_type=d["day_type"],
                work_location=d["work_location"],
                call=_num(d["call"]),
                meal_out=_num(d["meal_out"]),
                meal_in=_num(d["meal_in"]),
                wrap=_num(d["wrap"]),
            )
            for d in days
        ),
    )


def _case_from_row(row: dict[str, Any]) -> CaseRecord:
    findings = row["findings"]
    if isinstance(findings, str):
        findings = json.loads(findings)
    return CaseRecord(
        id=row["id"],
        timecard_id=row["timecard_id"],
        deal_memo_id=row["deal_memo_id"],
        week_ending=row["week_ending"],
        findings=list(findings),
        policy_action=row["policy_action"],
        amount_usd=Decimal(row["amount_usd"]),
        priority_score=int(row["priority_score"]),
        status=row["status"],
        review_reason=row.get("review_reason"),
        thread_id=row["thread_id"],
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )
