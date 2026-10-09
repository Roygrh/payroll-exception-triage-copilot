"""Connection pools: one for application tables, one for the LangGraph checkpointer."""

from __future__ import annotations

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def app_pool(database_url: str, *, min_size: int = 1, max_size: int = 8) -> ConnectionPool:
    return ConnectionPool(database_url, min_size=min_size, max_size=max_size, open=True)


def checkpointer_pool(database_url: str, *, max_size: int = 4) -> ConnectionPool:
    """The checkpointer requires autocommit, dict rows and no prepared statements."""
    return ConnectionPool(
        database_url,
        min_size=1,
        max_size=max_size,
        open=True,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
