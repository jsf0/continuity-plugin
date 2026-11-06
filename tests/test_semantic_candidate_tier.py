"""Regression tests for the semantic-candidate tier (v0.2.0).

'Vector proposes, the model disposes': the top vector-only matches above a
raw-cosine floor are OFFERED in a labeled low-confidence tier, bypassing the
absolute vector-only gate and all query-pattern rules. The consuming model
judges relevance; retrieval only answers 'is this related?'.
"""

from __future__ import annotations

from pathlib import Path

from continuity.config import SemanticCandidatesConfig
from continuity.embeddings import VectorHit
from continuity.models import ContextRecord
from continuity.retrieval import ContinuityRetriever
from continuity.store import ContinuityStore


class StubVectorBackend:
    def __init__(self, hits: list[VectorHit]) -> None:
        self._hits = hits

    def is_available(self) -> bool:
        return True

    def upsert(self, record_id: str, text: str) -> None:
        return None

    def delete(self, record_id: str) -> None:
        return None

    def search(self, query: str, limit: int) -> list[VectorHit]:
        return self._hits[:limit]


def _record(
    rid: str, kind: str, title: str, summary: str, tags: list[str] | None = None
) -> ContextRecord:
    return ContextRecord.from_dict(
        {
            "id": rid,
            "kind": kind,
            "title": title,
            "summary": summary,
            "tags": tags or [],
            "entities": [],
            "confidence": 0.9,
            "importance": 0.8,
        }
    )


def _store_with(tmp_path: Path, records: list[ContextRecord]) -> ContinuityStore:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    for record in records:
        store.upsert_record(record)
    return store


def test_tier_caps_offers_at_max_records(tmp_path: Path) -> None:
    store = _store_with(
        tmp_path,
        [
            _record("r_a", "user_preference", "Record A", "alpha summary"),
            _record("r_b", "user_preference", "Record B", "beta summary"),
            _record("r_c", "user_preference", "Record C", "gamma summary"),
        ],
    )
    retriever = ContinuityRetriever(
        store,
        vector_backend=StubVectorBackend(
            [VectorHit("r_a", 0.7), VectorHit("r_b", 0.65), VectorHit("r_c", 0.6)]
        ),
    )

    d = retriever.debug_search("anything at all about things", limit=5)
    offered = [c for c in d["selected"] if c.retrieval_role == "semantic_candidate"]
    assert [c.record.id for c in offered] == ["r_a", "r_b"]  # top-2 only


def test_tier_floor_rejects_off_domain_matches(tmp_path: Path) -> None:
    store = _store_with(tmp_path, [_record("r_a", "user_preference", "Record A", "alpha")])
    retriever = ContinuityRetriever(
        store, vector_backend=StubVectorBackend([VectorHit("r_a", 0.40)])
    )

    d = retriever.debug_search("capital of france", limit=5)
    assert not any(c.retrieval_role == "semantic_candidate" for c in d["selected"])
    assert any(c.rejected_reason == "weak_vector_only_without_anchor" for c in d["rejected"])


def test_tier_bypasses_reranker_gate(tmp_path: Path) -> None:
    """Semantic candidates must not be killed by a cold cross-encoder.

    Spike data (Nov 2026): the reranker scored the gold WRX record 0.164 on
    'for my car what do i need to watch for?' — barely above the 0.15 floor —
    while scoring llama-server records 0.94 on an animal question. The tier's
    contract is 'offered, not asserted'; the cross-encoder is the wrong judge
    for vector-bridged pairs.
    """

    class ColdReranker:
        def is_available(self) -> bool:
            return True

        def rerank(self, query: str, records: list[ContextRecord]) -> list[VectorHit]:
            return [VectorHit(r.id, 0.001) for r in records]  # reject everything

    store = _store_with(tmp_path, [_record("r_wrx", "user_preference", "WRX", "subaru sti")])
    retriever = ContinuityRetriever(
        store,
        vector_backend=StubVectorBackend([VectorHit("r_wrx", 0.7)]),
        reranker_backend=ColdReranker(),
    )

    d = retriever.debug_search("what car do I drive", limit=3)
    offered = [c for c in d["selected"] if c.retrieval_role == "semantic_candidate"]
    assert [c.record.id for c in offered] == ["r_wrx"]


def test_tier_disabled_restores_strict_gate(tmp_path: Path) -> None:
    store = _store_with(tmp_path, [_record("r_a", "user_preference", "Record A", "alpha")])
    retriever = ContinuityRetriever(
        store,
        vector_backend=StubVectorBackend([VectorHit("r_a", 0.7)]),
        semantic_config=SemanticCandidatesConfig(enabled=False),
    )
    d = retriever.debug_search("what car do I drive", limit=3)
    assert not any(c.retrieval_role == "semantic_candidate" for c in d["selected"])
    assert any(c.rejected_reason == "weak_vector_only_without_anchor" for c in d["rejected"])


def test_tier_guaranteed_slot_inside_limit(tmp_path: Path) -> None:
    """Anchored records must not squeeze the offer out of the limit."""
    store = _store_with(
        tmp_path,
        [
            _record("r_anchor1", "environment_fact", "Anchor One", "keyword match alpha"),
            _record("r_anchor2", "environment_fact", "Anchor Two", "keyword match beta"),
            _record("r_anchor3", "environment_fact", "Anchor Three", "keyword match gamma"),
            _record("r_sem", "user_preference", "Semantic", "no lexical overlap here"),
        ],
    )
    retriever = ContinuityRetriever(
        store,
        vector_backend=StubVectorBackend([VectorHit("r_sem", 0.6)]),
    )

    d = retriever.debug_search("keyword match", limit=3)
    ids = [c.record.id for c in d["selected"]]
    assert "r_sem" in ids  # guaranteed its slot despite 3 anchored candidates
