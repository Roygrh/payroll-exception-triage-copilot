"""Corpus ingestion into `corpus_chunks` (`uv run ptc ingest-corpus`)."""

from __future__ import annotations

from psycopg_pool import ConnectionPool

from payroll_triage.corpus.deal_memos import DealMemo
from payroll_triage.params import RuleParameters
from payroll_triage.retrieval.chunker import Chunk, build_corpus
from payroll_triage.retrieval.embeddings import Embedder


def ingest_corpus(
    pool: ConnectionPool,
    params: RuleParameters,
    memos: dict[str, DealMemo],
    embedder: Embedder,
    chunks: list[Chunk] | None = None,
) -> int:
    """Replace the corpus for the agreement version and the given memos; returns the row count."""
    chunks = chunks if chunks is not None else build_corpus(params, memos)
    vectors = embedder.embed_documents([c.text for c in chunks])
    a = params.agreement
    with pool.connection() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO agreement_versions (code, version, name, effective_from, effective_to)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (code, version) DO UPDATE SET name = EXCLUDED.name,
                effective_from = EXCLUDED.effective_from, effective_to = EXCLUDED.effective_to
            """,
            (a.code, a.version, a.name, a.effective_from, a.effective_to),
        )
        conn.execute(
            "DELETE FROM corpus_chunks WHERE citation_key = ANY(%s)",
            ([c.citation_key for c in chunks],),
        )
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO corpus_chunks (source_type, citation_key, agreement_code, version,
                    section, heading, body, effective_from, effective_to, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                """,
                [
                    (
                        c.source_type,
                        c.citation_key,
                        c.agreement_code,
                        c.version,
                        c.section,
                        c.heading,
                        c.body,
                        c.effective_from,
                        c.effective_to,
                        str(v),
                    )
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )
    return len(chunks)
