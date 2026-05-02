from __future__ import annotations

from pathlib import Path

from continuity.embeddings import SQLiteHashVectorBackend, VectorHit, cosine_similarity, embed_text
from continuity.models import ContextRecord
from continuity.retrieval import ContinuityRetriever
from continuity.store import ContinuityStore


class MockVectorBackend:
    def __init__(self, hits: list[VectorHit]) -> None:
        self.hits = hits
        self.deleted: list[str] = []

    def is_available(self) -> bool:
        return True

    def upsert(self, record_id: str, text: str) -> None:
        _ = (record_id, text)

    def delete(self, record_id: str) -> None:
        self.deleted.append(record_id)

    def search(self, query: str, limit: int) -> list[VectorHit]:
        _ = query
        return self.hits[:limit]


def test_hash_embeddings_are_deterministic_and_normalized() -> None:
    first = embed_text("delegate_task timeout", dimensions=32)
    second = embed_text("delegate_task timeout", dimensions=32)

    assert first == second
    assert cosine_similarity(first, second) == 1.0
    assert cosine_similarity(first, embed_text("", dimensions=32)) == 0.0


def test_sqlite_hash_backend_persists_vectors(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    record = ContextRecord.new(
        id="r_delegate_timeout",
        kind="lesson_learned",
        title="delegate_task timeout",
        summary="delegate_task can time out after 300s with api_calls:0.",
        tags=["delegate_task", "timeout"],
        scope_project="guard-proxy",
    )
    store.upsert_record(record)
    backend = SQLiteHashVectorBackend(store)

    backend.upsert(record.id, record.embedding_text or "")
    hits = backend.search("subagent hung", limit=3)

    assert store.count_vectors() == 1
    assert hits[0].record_id == record.id
    assert hits[0].score > 0


def test_vector_hits_participate_in_hybrid_retrieval(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        ContextRecord.new(
            id="r_plain",
            kind="lesson_learned",
            title="ordinary exact match",
            summary="This exact match should not hide a stronger vector hit.",
            tags=["exact"],
        )
    )
    store.upsert_record(
        ContextRecord.new(
            id="r_vector_only",
            kind="lesson_learned",
            title="semantic only",
            summary="This record is returned by a vector backend mock.",
            importance=0.9,
        )
    )
    retriever = ContinuityRetriever(
        store,
        vector_backend=MockVectorBackend([VectorHit(record_id="r_vector_only", score=0.99)]),
    )

    hits = retriever.search("exact", limit=2)

    assert any(hit.record.id == "r_vector_only" and "vector" in hit.reasons for hit in hits)
    assert any(hit.record.id == "r_plain" for hit in hits)


def test_stale_vector_hits_are_deleted(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    backend = MockVectorBackend([VectorHit(record_id="missing", score=1.0)])

    hits = ContinuityRetriever(store, vector_backend=backend).search("anything", limit=1)

    assert hits == []
    assert backend.deleted == ["missing"]
