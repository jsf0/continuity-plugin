import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from continuity.models import ContextRecord
from continuity.reranking import RerankHit
from continuity.retrieval import ContinuityRetriever
from continuity.store import ContinuityStore


class FakeVectorBackend:
    def is_available(self):
        return True

    def upsert(self, record_id, text):
        pass

    def delete(self, record_id):
        pass

    def search(self, query, limit):
        from continuity.embeddings import VectorHit

        return [
            VectorHit("framework", 0.75),
            VectorHit("work_prefs", 0.70),
            VectorHit("guard_proxy", 0.68),
        ][:limit]


class FakeReranker:
    def is_available(self):
        return True

    def rerank(self, query, records):
        return [
            RerankHit(
                record_id=record.id,
                score={
                    "framework": 0.04,
                    "work_prefs": 0.03,
                    "guard_proxy": 0.02,
                }.get(record.id, 0.0),
            )
            for record in records
        ]


def _record(record_id, summary, *, tags=None, entities=None):
    return ContextRecord.new(
        id=record_id,
        kind="environment_fact",
        title="Hermes global memory",
        summary=summary,
        tags=tags or [],
        entities=entities or [],
        confidence=0.9,
        importance=0.75,
        trust_level="built_in_memory_mirror",
    )


class LowInformationVectorBackend:
    def is_available(self):
        return True

    def upsert(self, record_id, text):
        pass

    def delete(self, record_id):
        pass

    def search(self, query, limit):
        from continuity.embeddings import VectorHit

        return [VectorHit("guard_proxy", 0.92)][:limit]


def test_low_information_followup_rejects_vector_only_mirrors(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "guard_proxy",
            "guard-proxy current status after SPKI docs cleanup. Can you test and see if it's better now?",
            tags=["guard-proxy"],
            entities=["guard-proxy"],
        )
    )

    hits = ContinuityRetriever(
        store,
        vector_backend=LowInformationVectorBackend(),
        association_enabled=True,
    ).search("continue and check if it's better now", limit=5)

    assert hits == []


def test_reranker_can_reject_weak_generic_query_candidates(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "framework",
            "Framework Desktop plan: experiment with llama.cpp, OpenBSD, and Vulkan.",
            tags=["hardware", "framework"],
            entities=["Framework Desktop"],
        )
    )
    store.upsert_record(
        _record(
            "work_prefs",
            "Work prefs: methodical/thorough/correct; tests pass and docs updated.",
        )
    )
    store.upsert_record(
        _record(
            "guard_proxy",
            "guard-proxy current status after SPKI docs cleanup.",
            tags=["guard-proxy"],
            entities=["guard-proxy"],
        )
    )

    hits = ContinuityRetriever(
        store,
        vector_backend=FakeVectorBackend(),
        reranker_backend=FakeReranker(),
        reranker_min_score=0.10,
    ).search("was continuity memory actually useful and working now?", limit=5)

    assert hits == []


def test_reranker_score_is_exposed_in_debug_output(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        _record(
            "framework",
            "Framework Desktop plan: experiment with llama.cpp, OpenBSD, and Vulkan.",
            tags=["hardware", "framework"],
            entities=["Framework Desktop"],
        )
    )

    debug = ContinuityRetriever(
        store,
        vector_backend=FakeVectorBackend(),
        reranker_backend=FakeReranker(),
        reranker_min_score=0.01,
    ).debug_search("Framework Desktop", limit=5)

    assert debug["selected"][0].reranker_score == 0.04
