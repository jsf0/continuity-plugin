"""Optional query/document reranking for continuity retrieval.

Rerankers run after cheap candidate generation (FTS/tags/entities/vectors) and
score each query-record pair directly.  They are intentionally optional because
cross-encoders are slower and require extra model dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from .models import ContextRecord

RERANKER_BACKENDS = frozenset({"sentence-transformers", "cross-encoder"})


@dataclass(frozen=True)
class RerankHit:
    """A query-record reranking result."""

    record_id: str
    score: float


class RerankerBackend(Protocol):
    """Small interface for optional pairwise rerankers."""

    def is_available(self) -> bool: ...

    def rerank(self, query: str, records: list[ContextRecord]) -> list[RerankHit]: ...


class SentenceTransformersRerankerBackend:
    """Local sentence-transformers CrossEncoder reranker backend."""

    def __init__(self, *, model: str = "BAAI/bge-reranker-base") -> None:
        self.model = model
        self._model: object | None = None

    def is_available(self) -> bool:
        try:
            import sentence_transformers  # noqa: F401
        except Exception:
            return False
        return True

    def rerank(self, query: str, records: list[ContextRecord]) -> list[RerankHit]:
        if not records:
            return []
        model = self._load_model()
        pairs = [(query, _record_text(record)) for record in records]
        raw_scores = model.predict(  # type: ignore[attr-defined]
            pairs,
            show_progress_bar=False,
        )
        scores = _scores_to_float_list(raw_scores)
        return [
            RerankHit(record_id=record.id, score=_normalize_score(score))
            for record, score in zip(records, scores, strict=True)
        ]

    def _load_model(self) -> object:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model)
        return self._model


def build_reranker_backend(config: object) -> RerankerBackend | None:
    """Create the configured optional reranker backend, if supported."""

    enabled = bool(getattr(config, "reranker_enabled", False))
    if not enabled:
        return None
    backend_name = str(getattr(config, "reranker_backend", "none") or "none")
    if backend_name not in RERANKER_BACKENDS:
        return None
    return SentenceTransformersRerankerBackend(
        model=str(getattr(config, "reranker_model", None) or "BAAI/bge-reranker-base")
    )


def _record_text(record: ContextRecord) -> str:
    return record.embedding_text or record.with_embedding_text().embedding_text or record.summary


def _scores_to_float_list(value: object) -> list[float]:
    try:
        iterable = value.tolist()  # type: ignore[attr-defined]
    except AttributeError:
        iterable = value
    if isinstance(iterable, (int, float)):
        return [float(iterable)]
    return [float(item) for item in iterable]  # type: ignore[union-attr]


def _normalize_score(score: float) -> float:
    """Normalize CrossEncoder output into an approximate 0..1 relevance score."""

    if 0.0 <= score <= 1.0:
        return score
    try:
        return 1.0 / (1.0 + math.exp(-score))
    except OverflowError:
        return 0.0 if score < 0 else 1.0
