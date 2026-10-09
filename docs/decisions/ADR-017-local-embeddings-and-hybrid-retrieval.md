# ADR-017: Local open-source embeddings and hybrid retrieval with reciprocal rank fusion

Status: Accepted
Date: 2026-10-08

## Context

Retrieval needs vector similarity over the agreement sections and deal memos (ADR-011 defers the effective-date and permission filters but the brief requires hybrid semantic plus keyword retrieval). An external embeddings API would add a second paid dependency and a second key; the corpus is small (96 agreement sections and ten deal memos), so a small local model is sufficient and keeps the free-to-run property of ADR-016.

## Decision

- **Model:** `BAAI/bge-small-en-v1.5` (MIT license), 384 dimensions, served by the `fastembed` package as quantized ONNX weights of about 67 MB, downloaded automatically on first use into fastembed's cache (`FASTEMBED_CACHE_PATH` when set, otherwise the system temp directory; a named volume in compose). The model name is pinned in configuration (`PTC_EMBEDDING_MODEL`, `PTC_EMBEDDING_DIM`) and the package version in `backend/uv.lock`. Query embeddings use the model's query mode (`query_embed`); documents use the plain mode.
- **Storage:** `corpus_chunks.embedding vector(384)` (pgvector) and a generated `tsvector` column over heading and body with a GIN index.
- **Hybrid search and ranking rule:** for a query, the vector search returns the top k chunks by cosine distance (`<=>`) and the full-text search returns the top k by `ts_rank_cd` against an OR of the query's words (English configuration). The two ranked lists are fused by reciprocal rank fusion: score(chunk) = sum over the lists containing it of 1 / (60 + rank), rank starting at 1; chunks are returned by fused score descending, ties broken by citation key. The retrieve node adds, by key, the sections the rule parameters map to the finding and the case's own deal memo chunk, so the model always sees the governing passages.
- **Chunking:** one chunk per anchored heading of the rendered agreement (the heading carries the citation key) and one chunk per deal memo (citation key equals the memo id; the body is a readable rendering of the memo's fields).

## Consequences

- No external embeddings API, no key; first run downloads about 67 MB once. Vectors are reproducible for a pinned package and model name.
- The 384-dimension vector column and the fusion constant are part of the migration and the search module; changing the model means a new migration (dimension) and a corpus re-ingest (`uv run ptc ingest-corpus`).
- The fusion rule is simple and explainable in the demo; a learned re-ranker is out of scope.
- Phase 2's effective-date and permission filters apply before ranking (ADR-011); the chunk table already carries the fields.
