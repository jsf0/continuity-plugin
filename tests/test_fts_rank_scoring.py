"""Regression test for the FTS bm25 rank-to-score conversion.

Observed live (Nov 2026): SQLite bm25() returns negative ranks where more
negative is a BETTER match, but the pipeline converted with abs(rank) and
1/(1+abs) — inverting the ordering. The top bm25 hit for a query ("oil")
received fts_score 0.20 while a weak filler-token match received 0.42, so
records about browsers outranked records about oil for an oil question.
"""

from __future__ import annotations

from pathlib import Path

from continuity.models import ContextRecord
from continuity.retrieval import ContinuityRetriever, _fts_rank_score
from continuity.store import ContinuityStore


def test_fts_rank_score_is_monotonic_in_match_quality() -> None:
    # bm25: more negative = better match.
    assert _fts_rank_score(-3.98) > _fts_rank_score(-1.38)
    assert _fts_rank_score(-1.38) > _fts_rank_score(-0.5)
    # Bounded in (0, 1).
    assert 0.0 <= _fts_rank_score(0.0) <= 1.0
    assert 0.0 < _fts_rank_score(-100.0) < 1.0
    # The previously-inverted pair: strong match must now beat weak match.
    assert _fts_rank_score(-3.98) > _fts_rank_score(-1.376)


def _record(record_id: str, title: str, summary: str) -> ContextRecord:
    return ContextRecord.from_dict(
        {
            "id": record_id,
            "kind": "environment_fact",
            "title": title,
            "summary": summary,
            "tags": [],
            "entities": [],
            "confidence": 0.9,
            "importance": 0.8,
        }
    )


def test_retriever_scores_better_fts_match_higher(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    # Record A is a strong match: the rare query term appears repeatedly.
    store.upsert_record(
        _record(
            "r_strong",
            "Oil eval toolkit",
            "Oil analysis. Oil ranking. Oil viscosity intervals for the WRX.",
        )
    )
    # Record B matches only a common filler word once.
    store.upsert_record(
        _record(
            "r_weak",
            "Headless browser notes",
            "Use this python path for all imports. Long unrelated text follows.",
        )
    )
    retriever = ContinuityRetriever(store)

    debug = retriever.debug_search("oil", limit=5)

    scores = {candidate.record.id: candidate.fts_score for candidate in debug["selected"]}
    assert scores.get("r_strong", 0.0) > scores.get("r_weak", 0.0), (
        "the best bm25 match must receive more FTS credit than a weaker one"
    )
