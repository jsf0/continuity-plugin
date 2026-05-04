from __future__ import annotations

from pathlib import Path

from continuity.embeddings import VectorHit
from continuity.models import ContextRecord
from continuity.store import ContinuityStore
from continuity.tools import handle_debug_retrieval, handle_reindex_vectors


class MockVectorBackend:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, str]] = []

    def is_available(self) -> bool:
        return True

    def upsert(self, record_id: str, text: str) -> None:
        self.upserts.append((record_id, text))

    def delete(self, record_id: str) -> None:
        _ = record_id

    def search(self, query: str, limit: int) -> list[VectorHit]:
        _ = (query, limit)
        return []


def _store(tmp_path: Path) -> ContinuityStore:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        ContextRecord.new(
            id="raptor",
            kind="user_preference",
            title="Tow vehicle",
            summary="User has a 2018 Ford Raptor and a trailerable boat setup.",
            tags=["vehicle", "towing", "boat"],
            entities=["2018 Ford Raptor"],
        )
    )
    store.upsert_record(
        ContextRecord.new(
            id="guard",
            kind="project_convention",
            title="guard-proxy status",
            summary="guard-proxy project status.",
            scope_project="root",
        )
    )
    return store


def test_debug_retrieval_explains_selected_and_rejected_candidates(tmp_path: Path) -> None:
    result = handle_debug_retrieval(
        _store(tmp_path), {"query": "what boats can I tow with my setup?", "scope_project": "root"}
    )

    assert result["success"] is True
    selected_ids = [item["id"] for item in result["selected"]]
    assert "raptor" in selected_ids
    assert "expanded_tokens" in result


def test_reindex_vectors_indexes_active_records(tmp_path: Path) -> None:
    backend = MockVectorBackend()
    result = handle_reindex_vectors(
        _store(tmp_path), {}, vector_backend=backend, backend_name="mock", model="mock-model"
    )

    assert result == {
        "success": True,
        "indexed": 2,
        "skipped": 0,
        "backend": "mock",
        "model": "mock-model",
    }
    assert [record_id for record_id, _ in backend.upserts] == ["guard", "raptor"]
