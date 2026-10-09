"""Minimal SQL migration runner (`uv run ptc migrate`).

Files in `db/migrations/NNNN_name.sql` are applied in order, each inside one
transaction, and recorded in `schema_migrations`. After the SQL migrations the
LangGraph PostgreSQL checkpointer creates its own tables (ADR-013).
"""

from __future__ import annotations

import re
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


def migration_files(directory: Path | None = None) -> list[Path]:
    directory = directory or MIGRATIONS_DIR
    files = [p for p in directory.iterdir() if _NAME.match(p.name)]
    return sorted(files, key=lambda p: p.name)


def _ensure_table(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    text PRIMARY KEY,
            applied_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def applied_versions(conn: psycopg.Connection) -> set[str]:
    _ensure_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {r["version"] if isinstance(r, dict) else r[0] for r in rows}


def apply_migrations(database_url: str, directory: Path | None = None) -> list[str]:
    """Apply pending migrations; returns the versions applied in this run."""
    applied: list[str] = []
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        done = applied_versions(conn)
        conn.commit()
        for path in migration_files(directory):
            version = path.name.split("_", 1)[0]
            if version in done:
                continue
            sql = path.read_text(encoding="utf-8")
            with conn.transaction():
                conn.execute(sql)  # type: ignore[arg-type]
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied.append(version)
    return applied


def setup_checkpointer(database_url: str) -> None:
    """Create the LangGraph checkpoint tables (idempotent)."""
    from langgraph.checkpoint.postgres import PostgresSaver

    with PostgresSaver.from_conn_string(database_url) as saver:
        saver.setup()


def migrate(database_url: str, directory: Path | None = None) -> list[str]:
    applied = apply_migrations(database_url, directory)
    setup_checkpointer(database_url)
    return applied
