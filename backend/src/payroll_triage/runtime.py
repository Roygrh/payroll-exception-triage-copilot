"""Wire the runtime: settings, pools, checkpointer, adapter, retriever, graph, service."""

from __future__ import annotations

from dataclasses import dataclass

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from payroll_triage.config import Settings, get_settings
from payroll_triage.data.scenarios import load_catalog
from payroll_triage.db.connection import app_pool, checkpointer_pool
from payroll_triage.db.store import PostgresCaseStore
from payroll_triage.graph.build import build_graph
from payroll_triage.graph.nodes import Clock, Deps
from payroll_triage.graph.service import TriageService
from payroll_triage.llm.v1 import LLMAdapter, build_adapter
from payroll_triage.params import get_parameters
from payroll_triage.retrieval.embeddings import get_embedder
from payroll_triage.retrieval.search import PostgresRetriever


def demo_clock() -> Clock:
    catalog = load_catalog()
    return Clock(
        as_of=catalog.as_of_date,
        payroll_run_date=catalog.payroll_run_date,
        holidays=catalog.holidays,
        work_day_type=catalog.labels["day_type"]["work"],
        intake_status=catalog.queue_status,
        timecard_status_after={**catalog.labels["timecard_status_after"], "escalate": None},
    )


@dataclass
class Runtime:
    settings: Settings
    pool: ConnectionPool
    saver_pool: ConnectionPool
    service: TriageService

    def close(self) -> None:
        self.pool.close()
        self.saver_pool.close()


def build_runtime(adapter: LLMAdapter | None = None) -> Runtime:
    settings = get_settings()
    pool = app_pool(settings.database_url)
    saver_pool = checkpointer_pool(settings.database_url)
    saver = PostgresSaver(saver_pool)  # type: ignore[arg-type]
    deps = Deps(
        store=PostgresCaseStore(pool),
        retriever=PostgresRetriever(pool, get_embedder()),
        adapter=adapter or build_adapter(settings),
        params=get_parameters(),
        clock=demo_clock(),
        max_output_tokens=settings.llm_max_output_tokens,
    )
    graph = build_graph(deps, saver)
    return Runtime(settings, pool, saver_pool, TriageService(graph, deps))
