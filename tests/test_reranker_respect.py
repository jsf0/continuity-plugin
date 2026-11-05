"""Regression tests for reranker-respect behaviors (v0.1.4).

Observed live (Nov 2026): the pipeline's remaining noise and misses both
funneled through the cross-encoder stage.

1. bge-reranker-base under-scored terse records that genuinely answered a
   query (oil-eval records at 0.0027 for an oil question) while scoring
   records that merely quoted query words highly.  Strong bm25 matches now
   earn a reranker bypass (strong_fts_anchor).
2. The association-graph stage ran after reranking and un-rejected ANY
   reranker-rejected record it reached, resurrecting browser mirrors the
   cross-encoder had scored 3.7e-5.  Graph inclusion now respects
   essentially-zero reranker verdicts below graph_reranker_respect_floor,
   while cold-but-nonzero records remain rescuable by design.
3. The flat per-token text bonus credited generic filler as much as
   distinctive terms; text anchors are now IDF-weighted.
"""

from __future__ import annotations

from pathlib import Path

from continuity.models import ContextRecord
from continuity.reranking import RerankHit
from continuity.retrieval import ContinuityRetriever
from continuity.store import ContinuityStore


class ScoreByIdReranker:
    """Reranker stub returning fixed scores per record id."""

    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores

    def is_available(self) -> bool:
        return True

    def rerank(self, query: str, records: list[ContextRecord]) -> list[RerankHit]:
        return [RerankHit(record_id=r.id, score=self.scores.get(r.id, 0.001)) for r in records]


def _record(
    record_id: str, title: str, summary: str, tags: list[str] | None = None
) -> ContextRecord:
    return ContextRecord.from_dict(
        {
            "id": record_id,
            "kind": "environment_fact",
            "title": title,
            "summary": summary,
            "tags": tags or [],
            "entities": [],
            "confidence": 0.9,
            "importance": 0.8,
        }
    )


def _seeded_store(tmp_path: Path) -> ContinuityStore:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    # bm25 idf is corpus-relative; filler records give the query term real
    # inverse document frequency so strong matches clear the FTS threshold.
    for index in range(10):
        store.upsert_record(
            _record(
                f"r_filler_{index}",
                f"Filler record {index} about topic{index}",
                f"Filler content {index} entirely about topic{index} matters.",
            )
        )
    return store


def test_strong_fts_match_survives_cold_reranker(tmp_path: Path) -> None:
    store = _seeded_store(tmp_path)
    store.upsert_record(
        _record(
            "r_oil",
            "Oil eval toolkit",
            "Oil analysis. Oil ranking. Oil viscosity intervals for the WRX EJ257.",
        )
    )

    debug = ContinuityRetriever(
        store,
        reranker_backend=ScoreByIdReranker({"r_oil": 0.001}),
        reranker_min_score=0.15,
    ).debug_search("oil viscosity intervals", limit=5)

    selected = {c.record.id: c for c in debug["selected"]}
    assert "r_oil" in selected, "strong bm25 match must survive the reranker"
    assert "strong_fts_anchor" in selected["r_oil"].reasons


def test_weak_fts_match_still_obys_reranker(tmp_path: Path) -> None:
    # The live noise pattern: a candidate carried by vector similarity with
    # only a weak, corpus-generic lexical footprint (browser-tool records
    # on "use"-heavy queries).  It must reach the reranker, be rejected
    # there, and NOT be rescued by the FTS-anchor bypass.
    from continuity.embeddings import VectorHit

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

    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    # Corpus where "oil" is common, so a single incidental mention is a weak
    # lexical match that cannot earn the FTS bypass.
    for index in range(10):
        store.upsert_record(
            _record(
                f"r_filler_{index}",
                f"Filler {index} about oil topic{index}",
                f"Oil filler content {index}. Oil notes. topic{index} matters.",
            )
        )
    store.upsert_record(
        _record(
            "r_browser",
            "Headless browser notes",
            "One incidental oil mention. Use this python path for all imports.",
            tags=["browser"],
        )
    )

    debug = ContinuityRetriever(
        store,
        vector_backend=StubVectorBackend([VectorHit("r_browser", 0.5)]),
        reranker_backend=ScoreByIdReranker({"r_browser": 0.001}),
        reranker_min_score=0.15,
        association_enabled=False,
    ).debug_search("oil viscosity intervals", limit=5)

    rejected = {c.record.id: c for c in debug["rejected"]}
    assert "r_browser" in rejected
    assert rejected["r_browser"].rejected_reason == "below_min_reranker_score"
    assert "strong_fts_anchor" not in rejected["r_browser"].reasons


def test_graph_respects_near_zero_reranker_verdicts(tmp_path: Path) -> None:
    store = _seeded_store(tmp_path)
    store.upsert_record(
        _record(
            "r_seed",
            "Oil eval toolkit",
            "Oil analysis. Oil ranking. Oil viscosity intervals.",
            tags=["oil"],
        )
    )
    # Strongly graph-connected neighbor the cross-encoder scored ~zero.
    store.upsert_record(
        _record(
            "r_zero_neighbor",
            "Oil brand preferences",
            "Oil brand notes and oil storage details.",
            tags=["oil"],
        )
    )
    # Strongly graph-connected neighbor the cross-encoder scored cold-but-nonzero.
    store.upsert_record(
        _record(
            "r_cold_neighbor",
            "Oil change intervals",
            "Oil change interval tracking notes.",
            tags=["oil"],
        )
    )
    store.upsert_association_edge(
        "r_seed", "r_zero_neighbor", strength=0.95, edge_type="tag_overlap"
    )
    store.upsert_association_edge(
        "r_seed", "r_cold_neighbor", strength=0.95, edge_type="tag_overlap"
    )

    debug = ContinuityRetriever(
        store,
        reranker_backend=ScoreByIdReranker(
            {"r_seed": 0.9, "r_zero_neighbor": 0.00001, "r_cold_neighbor": 0.01}
        ),
        reranker_min_score=0.15,
        association_enabled=True,
        association_activation_threshold=0.3,
        association_hop_decay=0.6,
    ).debug_search("oil viscosity intervals", limit=8)

    selected_ids = {c.record.id for c in debug["selected"]}
    assert "r_seed" in selected_ids
    assert "r_zero_neighbor" not in selected_ids, (
        "a record the reranker scored essentially zero must not be resurrected by the graph"
    )
    assert "r_cold_neighbor" in selected_ids, (
        "a cold-but-nonzero reranker score must remain graph-rescuable"
    )
    cut_reasons = {
        (n.get("record_id"), n.get("reason")) for n in debug["activation_trace"]["cut_neighbors"]
    }
    assert ("r_zero_neighbor", "reranker_rejected_respected") in cut_reasons


def test_text_anchor_bonus_is_idf_weighted(tmp_path: Path) -> None:
    from continuity.retrieval import CandidateScore, _apply_metadata_score
    from continuity.vocabulary import CorpusTermStats

    # Corpus where "quuxwidget" is distinctive and "use" is in most records.
    distinctive_record = _record(
        "r_distinctive", "Quuxwidget setup", "Quuxwidget needs oil intervals."
    )
    fillers = [
        _record(f"r_f{i}", f"Filler {i}", f"Use this filler. Use that. topic{i} content.")
        for i in range(10)
    ]
    stats = CorpusTermStats.from_records([distinctive_record, *fillers])

    distinctive_hit = CandidateScore(
        _record("r_a", "A", "quuxwidget oil intervals and general notes about oil")
    )
    generic_only_hit = CandidateScore(_record("r_b", "B", "use this and use that for anything"))

    _apply_metadata_score(distinctive_hit, {"quuxwidget"}, stats)
    _apply_metadata_score(generic_only_hit, {"use"}, stats)

    assert distinctive_hit.text_score > 0.3, "distinctive text anchor earns near-full credit"
    assert generic_only_hit.text_score < 0.15, "corpus-generic text anchor earns almost nothing"
