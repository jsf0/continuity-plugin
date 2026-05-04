"""Optional local vector retrieval support for continuity memory.

Phase 7 keeps vector retrieval optional and dependency-free. The default
``sqlite-hash`` backend stores deterministic hashed embeddings in SQLite so the
plugin still works when third-party vector packages are unavailable. Tests can
inject a mock backend through the same small interface.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Protocol

from .models import ContextRecord, utc_now
from .store import ContinuityStore

DEFAULT_DIMENSIONS = 64
VECTOR_BACKENDS = frozenset({"sqlite-hash", "hash", "sqlite-json", "sentence-transformers"})

SYNONYMS = {
    "hang": "timeout",
    "hung": "timeout",
    "stuck": "timeout",
    "worker": "subagent",
    "workers": "subagent",
    "child": "subagent",
    "children": "subagent",
    "agent": "subagent",
    "delegation": "delegate_task",
    "delegate": "delegate_task",
    "rag": "retrieval",
    "semantic": "vector",
    "vectors": "vector",
    "embedding": "vector",
    "embeddings": "vector",
}


@dataclass(frozen=True)
class VectorHit:
    """A vector search result."""

    record_id: str
    score: float


class VectorBackend(Protocol):
    """Small vector backend interface used by retrieval."""

    def is_available(self) -> bool: ...

    def upsert(self, record_id: str, text: str) -> None: ...

    def delete(self, record_id: str) -> None: ...

    def search(self, query: str, limit: int) -> list[VectorHit]: ...


class SQLiteHashVectorBackend:
    """SQLite-backed deterministic hashed-vector backend.

    This is intentionally modest: it is local, inspectable, has no native
    extension dependency, and provides a real persisted vector index for Phase 7.
    It can later be replaced by sqlite-vec or LanceDB without changing retrieval.
    """

    def __init__(
        self,
        store: ContinuityStore,
        *,
        model: str = "hash-v1",
        dimensions: int = DEFAULT_DIMENSIONS,
    ) -> None:
        self.store = store
        self.model = model
        self.dimensions = max(8, dimensions)

    def is_available(self) -> bool:
        return True

    def upsert(self, record_id: str, text: str) -> None:
        vector = embed_text(text, dimensions=self.dimensions)
        self.store.upsert_vector(
            record_id=record_id,
            model=self.model,
            dimensions=self.dimensions,
            vector=vector,
        )

    def delete(self, record_id: str) -> None:
        self.store.delete_vector(record_id, model=self.model)

    def search(self, query: str, limit: int) -> list[VectorHit]:
        query_vector = embed_text(query, dimensions=self.dimensions)
        hits: list[VectorHit] = []
        for row in self.store.list_vectors(model=self.model):
            if int(row["dimensions"]) != self.dimensions:
                continue
            vector = _parse_vector(str(row["vector_json"]))
            score = cosine_similarity(query_vector, vector)
            if score > 0:
                hits.append(VectorHit(record_id=str(row["record_id"]), score=score))
        hits.sort(key=lambda hit: (-hit.score, hit.record_id))
        return hits[:limit]


class SentenceTransformersVectorBackend:
    """Optional local semantic embedding backend using sentence-transformers."""

    def __init__(
        self,
        store: ContinuityStore,
        *,
        model: str = "BAAI/bge-small-en-v1.5",
        normalize: bool = True,
    ) -> None:
        self.store = store
        self.model = model
        self.normalize = normalize
        self._model: object | None = None

    def is_available(self) -> bool:
        try:
            import sentence_transformers  # noqa: F401
        except Exception:
            return False
        return True

    def upsert(self, record_id: str, text: str) -> None:
        vector = self.embed([text])[0]
        self.store.upsert_vector(
            record_id=record_id,
            model=self.model,
            dimensions=len(vector),
            vector=vector,
        )

    def delete(self, record_id: str) -> None:
        self.store.delete_vector(record_id, model=self.model)

    def search(self, query: str, limit: int) -> list[VectorHit]:
        query_vector = self.embed([query])[0]
        hits: list[VectorHit] = []
        for row in self.store.list_vectors(model=self.model):
            vector = _parse_vector(str(row["vector_json"]))
            score = cosine_similarity(query_vector, vector)
            if score > 0:
                hits.append(VectorHit(record_id=str(row["record_id"]), score=score))
        hits.sort(key=lambda hit: (-hit.score, hit.record_id))
        return hits[:limit]

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        vectors = model.encode(  # type: ignore[attr-defined]
            texts,
            normalize_embeddings=self.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [_vector_to_float_list(vector) for vector in vectors]

    def _load_model(self) -> object:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model)
        return self._model


def build_vector_backend(config: object, store: ContinuityStore) -> VectorBackend | None:
    """Create the configured optional vector backend, if supported."""

    enabled = bool(getattr(config, "vector_enabled", False))
    if not enabled:
        return None
    backend_name = str(getattr(config, "vector_backend", "none") or "none")
    if backend_name not in VECTOR_BACKENDS:
        return None
    model = str(getattr(config, "embedding_model", None) or "hash-v1")
    if backend_name == "sentence-transformers":
        return SentenceTransformersVectorBackend(
            store,
            model=str(getattr(config, "embedding_model", None) or "BAAI/bge-small-en-v1.5"),
            normalize=bool(getattr(config, "embedding_normalize", True)),
        )
    return SQLiteHashVectorBackend(store, model=model)


def index_records(backend: VectorBackend | None, records: list[ContextRecord]) -> None:
    """Synchronize records into an optional vector backend."""

    if backend is None or not backend.is_available():
        return
    for record in records:
        backend.upsert(
            record.id, record.embedding_text or record.with_embedding_text().embedding_text or ""
        )


def embed_text(text: str, *, dimensions: int = DEFAULT_DIMENSIONS) -> list[float]:
    """Embed text using deterministic signed feature hashing."""

    vector = [0.0] * max(8, dimensions)
    for token in _embedding_tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % len(vector)
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity for normalized or raw vectors."""

    if not left or not right or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    return dot / (left_norm * right_norm)


def serialize_vector(vector: list[float]) -> str:
    """Serialize a vector for SQLite storage."""

    return json.dumps(vector, separators=(",", ":"))


def now_for_vector_row() -> str:
    """Return a timestamp for vector row updates."""

    return utc_now()


def _embedding_tokens(text: str) -> list[str]:
    raw_tokens = [token.lower() for token in re.findall(r"[\w:-]+", text)]
    tokens: list[str] = []
    for token in raw_tokens:
        normalized = SYNONYMS.get(token, token)
        tokens.append(normalized)
        tokens.extend(_char_ngrams(normalized))
    return tokens


def _char_ngrams(token: str) -> list[str]:
    compact = re.sub(r"[^a-z0-9]", "", token)
    if len(compact) < 4:
        return []
    return [f"ng:{compact[index : index + 4]}" for index in range(len(compact) - 3)]


def _vector_to_float_list(value: object) -> list[float]:
    try:
        iterable = value.tolist()  # type: ignore[attr-defined]
    except AttributeError:
        iterable = value
    return [float(item) for item in iterable]  # type: ignore[union-attr]


def _parse_vector(value: str) -> list[float]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    output: list[float] = []
    for item in parsed:
        try:
            output.append(float(item))
        except (TypeError, ValueError):
            return []
    return output
