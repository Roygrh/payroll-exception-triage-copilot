"""Local embeddings with a small open-source model (ADR-017).

Model: BAAI/bge-small-en-v1.5 (MIT license), 384 dimensions, quantized ONNX
weights of about 67 MB served by fastembed; downloaded automatically on first
use into fastembed's cache (`FASTEMBED_CACHE_PATH`, or the system temp
directory by default, or the compose volume). The model name and the
fastembed version are pinned (`uv.lock`), so the vectors are reproducible.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from typing import Protocol

from payroll_triage.config import get_settings

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_DIM = 384


class Embedder(Protocol):
    model_name: str
    dim: int

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    def __init__(self, model_name: str = DEFAULT_MODEL, dim: int = DEFAULT_DIM) -> None:
        from fastembed import TextEmbedding

        self.model_name = model_name
        self.dim = dim
        self._model = TextEmbedding(model_name=model_name)
        probe = next(iter(self._model.embed(["dimension probe"])))
        if len(probe) != dim:
            raise ValueError(
                f"embedding model {model_name} produces {len(probe)} dimensions, expected {dim}"
            )

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._model.embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        return list(map(float, next(iter(self._model.query_embed(text)))))


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    s = get_settings()
    return FastEmbedEmbedder(s.embedding_model, s.embedding_dim)
