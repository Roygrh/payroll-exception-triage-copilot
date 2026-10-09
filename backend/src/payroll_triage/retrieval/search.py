"""Hybrid retrieval: pgvector similarity plus PostgreSQL full-text search (ADR-017).

Full-text query: the query words joined with OR (stop words removed by the
English configuration), ranked with `ts_rank_cd`. Vector query: cosine
distance on the pgvector column.

Ranking rule (reciprocal rank fusion): each of the two searches returns its
top `k` chunks in rank order; a chunk's fused score is the sum over the lists
in which it appears of 1 / (RRF_K + rank), rank starting at 1. Chunks are
returned by fused score, descending; ties break by citation key. RRF_K = 60
(the usual constant) so that a chunk ranked first by both searches scores
2 / 61 and one ranked first by only one search scores 1 / 61.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from payroll_triage.retrieval.chunker import Chunk
from payroll_triage.retrieval.embeddings import Embedder

RRF_K = 60
DEFAULT_TOP_K = 6


@dataclass(frozen=True)
class RankedChunk:
    chunk: Chunk
    score: float
    vector_rank: int | None
    text_rank: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.chunk.to_dict(),
            "score": round(self.score, 6),
            "vector_rank": self.vector_rank,
            "text_rank": self.text_rank,
        }


def fuse_rankings(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal rank fusion over lists of citation keys (each list in rank order)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for position, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + position)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


class Retriever(Protocol):
    def search(self, query: str, *, top_k: int = DEFAULT_TOP_K) -> list[RankedChunk]: ...
    def get(self, citation_key: str) -> Chunk | None: ...


def _chunk_from_row(row: dict[str, Any]) -> Chunk:
    return Chunk(
        source_type=row["source_type"],
        citation_key=row["citation_key"],
        agreement_code=row["agreement_code"],
        version=row["version"],
        section=row["section"],
        heading=row["heading"],
        body=row["body"],
        effective_from=row["effective_from"],
        effective_to=row["effective_to"],
    )


_COLUMNS = (
    "source_type, citation_key, agreement_code, version, section, heading, body, "
    "effective_from, effective_to"
)


class PostgresRetriever:
    def __init__(self, pool: ConnectionPool, embedder: Embedder) -> None:
        self.pool = pool
        self.embedder = embedder

    def get(self, citation_key: str) -> Chunk | None:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_COLUMNS} FROM corpus_chunks WHERE citation_key = %s", (citation_key,)
            ).fetchone()
        return _chunk_from_row(row) if row else None

    def vector_search(self, query: str, top_k: int) -> list[Chunk]:
        vector = self.embedder.embed_query(query)
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"SELECT {_COLUMNS} FROM corpus_chunks "
                "ORDER BY embedding <=> %s::vector, citation_key LIMIT %s",
                (str(vector), top_k),
            ).fetchall()
        return [_chunk_from_row(r) for r in rows]

    def text_search(self, query: str, top_k: int) -> list[Chunk]:
        tsquery = or_tsquery(query)
        if not tsquery:
            return []
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"SELECT {_COLUMNS}, ts_rank_cd(tsv, q) AS rank FROM corpus_chunks, "
                "to_tsquery('english', %s) AS q WHERE tsv @@ q "
                "ORDER BY rank DESC, citation_key LIMIT %s",
                (tsquery, top_k),
            ).fetchall()
        return [_chunk_from_row(r) for r in rows]

    def search(self, query: str, *, top_k: int = DEFAULT_TOP_K) -> list[RankedChunk]:
        by_vector = self.vector_search(query, top_k)
        by_text = self.text_search(query, top_k)
        return combine(by_vector, by_text, top_k)


def or_tsquery(query: str) -> str:
    """Full-text query as an OR of the query's words, so passages that contain more of the
    words rank higher (`ts_rank_cd`) instead of requiring every word to be present."""
    words: list[str] = []
    for token in re.findall(r"[a-z0-9]+", query.lower()):
        if token not in words:
            words.append(token)
    return " | ".join(words)


def combine(by_vector: list[Chunk], by_text: list[Chunk], top_k: int) -> list[RankedChunk]:
    chunks = {c.citation_key: c for c in by_vector + by_text}
    v_rank = {c.citation_key: i for i, c in enumerate(by_vector, start=1)}
    t_rank = {c.citation_key: i for i, c in enumerate(by_text, start=1)}
    fused = fuse_rankings([[c.citation_key for c in by_vector], [c.citation_key for c in by_text]])
    return [
        RankedChunk(chunks[key], score, v_rank.get(key), t_rank.get(key))
        for key, score in fused[:top_k]
    ]


def effective_version_on(day: dt.date, chunks_version: str) -> str:
    """Phase 1 has one agreement version; the effective-date filter arrives in Phase 2 (ADR-011)."""
    return chunks_version
