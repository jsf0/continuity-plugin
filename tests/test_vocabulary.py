from __future__ import annotations

from continuity.models import ContextRecord
from continuity.vocabulary import CorpusTermStats, weighted_jaccard


def _record(record_id: str, summary: str, *, tags: list[str] | None = None) -> ContextRecord:
    return ContextRecord.new(
        id=record_id,
        kind="user_preference",
        title=record_id,
        summary=summary,
        tags=tags or [],
        confidence=0.9,
        importance=0.8,
        trust_level="explicit_user",
    )


def test_empty_corpus_stats_are_safe() -> None:
    stats = CorpusTermStats.from_records([])

    assert stats.document_count == 0
    assert stats.idf("anything") == 0.0
    assert stats.is_generic("the") is True
    assert stats.is_generic("rare") is False


def test_generic_detection_uses_document_frequency_after_small_corpus_threshold() -> None:
    stats = CorpusTermStats.from_records(
        [
            _record("r1", "shared rare1", tags=["shared"]),
            _record("r2", "shared rare2", tags=["shared"]),
            _record("r3", "shared rare3", tags=["shared"]),
            _record("r4", "shared rare4", tags=["shared"]),
        ]
    )

    assert stats.is_generic("shared") is True
    assert stats.is_generic("rare1") is False


def test_weighted_jaccard_prefers_rare_shared_terms() -> None:
    stats = CorpusTermStats.from_records(
        [
            _record("r1", "common rare-alpha", tags=["common", "rare-alpha"]),
            _record("r2", "common rare-alpha", tags=["common", "rare-alpha"]),
            _record("r3", "common other", tags=["common"]),
            _record("r4", "common other", tags=["common"]),
        ]
    )

    rare_overlap = weighted_jaccard({"common", "rare alpha"}, {"common", "rare alpha"}, stats)
    common_only = weighted_jaccard({"common", "left"}, {"common", "right"}, stats)

    assert rare_overlap > common_only
