from __future__ import annotations

import sys
import types
from pathlib import Path

from continuity.embeddings import SentenceTransformersVectorBackend
from continuity.models import ContextRecord
from continuity.store import ContinuityStore


class FakeVector(list[float]):
    def tolist(self) -> list[float]:
        return list(self)


class FakeSentenceTransformer:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def encode(
        self,
        texts: list[str],
        *,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
        show_progress_bar: bool,
    ) -> list[FakeVector]:
        _ = (normalize_embeddings, convert_to_numpy, show_progress_bar)
        vectors = []
        for text in texts:
            lowered = text.lower()
            if "raptor" in lowered or "tow" in lowered or "trailerable" in lowered:
                vectors.append(FakeVector([1.0, 0.0]))
            elif "guard-proxy" in lowered:
                vectors.append(FakeVector([0.0, 1.0]))
            else:
                vectors.append(FakeVector([0.0, 0.0]))
        return vectors


def test_sentence_transformers_backend_indexes_and_searches_with_mock(
    tmp_path: Path, monkeypatch
) -> None:
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    raptor = ContextRecord.new(
        id="raptor",
        kind="user_preference",
        title="Tow vehicle",
        summary="User has a 2018 Ford Raptor and can store a trailerable boat.",
    )
    guard = ContextRecord.new(
        id="guard",
        kind="project_convention",
        title="guard-proxy status",
        summary="guard-proxy current status and Rust proxy details.",
    )
    store.upsert_record(raptor)
    store.upsert_record(guard)
    backend = SentenceTransformersVectorBackend(store, model="fake-model")

    assert backend.is_available() is True
    backend.upsert(raptor.id, raptor.embedding_text or "")
    backend.upsert(guard.id, guard.embedding_text or "")

    hits = backend.search("what can i tow with my setup?", limit=2)

    assert hits[0].record_id == "raptor"
    assert store.count_vectors(model="fake-model") == 2
