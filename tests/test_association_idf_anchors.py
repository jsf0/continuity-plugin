"""Regression tests for IDF-anchored association edge scoring.

Observed live failure (Nov 2026): the old strength formula granted a flat
+0.35 bonus for ANY entity overlap, so records connected only through
generic entities ("nov", "uv", "2026") crossed the 0.25 creation threshold.
Dense, entity-rich records became graph hubs that activated as associative
neighbors on unrelated queries (e.g. a browser/search-policy record at
activation 0.558 on a backup-encryption query, outranking the correct
neighbor).  Anchor bonuses are now scaled by the share of IDF mass carried
by non-generic shared terms, and IDF is computed over the whole corpus.
"""

from __future__ import annotations

from pathlib import Path

from continuity.association import association_evidence
from continuity.models import ContextRecord
from continuity.store import ContinuityStore
from continuity.vocabulary import CorpusTermStats


def _record(
    record_id: str, title: str, entities: list[str], tags: list[str] | None = None
) -> ContextRecord:
    return ContextRecord.from_dict(
        {
            "id": record_id,
            "kind": "environment_fact",
            "title": title,
            "summary": title,
            "tags": tags or [],
            "entities": entities,
            "confidence": 0.9,
            "importance": 0.8,
        }
    )


def _hub_corpus_store(tmp_path: Path) -> ContinuityStore:
    """A store where a generic date entity appears in most records."""
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    # Eight filler records make "nov 2026" appear in >20% of the corpus,
    # so it is generic for edge-anchor purposes.
    for index in range(8):
        store.upsert_record(
            _record(
                f"r_filler_{index}",
                f"Filler record {index} about topic{index}",
                entities=["nov 2026", f"topic{index}"],
            )
        )
    return store


def test_generic_only_entity_overlap_does_not_create_an_edge(tmp_path: Path) -> None:
    store = _hub_corpus_store(tmp_path)
    store.upsert_record(
        _record("r_backup", "Weekly backup runs through jfcrypt", entities=["nov 2026", "jfcrypt"])
    )
    store.upsert_record(
        _record(
            "r_search",
            "Search uses the exa provider now",
            entities=["nov 2026", "exa"],
        )
    )

    edges = store.list_association_edges("r_backup")

    assert not any(edge.memory_id_b == "r_search" for edge in edges), (
        "records sharing only the generic entity 'nov 2026' must not be linked"
    )


def test_distinctive_entity_overlap_still_creates_an_edge(tmp_path: Path) -> None:
    store = _hub_corpus_store(tmp_path)
    store.upsert_record(
        _record("r_backup", "Weekly backup runs through jfcrypt", entities=["nov 2026", "jfcrypt"])
    )
    store.upsert_record(
        _record(
            "r_key",
            "Backup key fingerprint verified intact",
            entities=["nov 2026", "jfcrypt", "fingerprint"],
        )
    )

    edges = store.list_association_edges("r_backup")

    assert any(edge.memory_id_b == "r_key" and edge.strength >= 0.25 for edge in edges), (
        "records sharing the distinctive entity 'jfcrypt' must be linked"
    )


def test_anchor_quality_zero_for_purely_generic_overlap() -> None:
    left = _record("r_left", "Left record", entities=["nov 2026", "left-only"])
    right = _record("r_right", "Right record", entities=["nov 2026", "right-only"])
    stats = CorpusTermStats.from_records([left, right])

    # With only two documents the generic fraction check is not applied, so
    # extend with filler docs so "nov 2026" crosses the 20% fraction.
    fillers = [
        _record(f"r_f{i}", f"Filler {i}", entities=["nov 2026", f"topic{i}"]) for i in range(8)
    ]
    stats = CorpusTermStats.from_records([left, right, *fillers])

    evidence = association_evidence(left, right, stats=stats)

    assert evidence.shared_entities == ("nov 2026",)
    assert evidence.strength < 0.25


def test_rebuild_association_edges_drops_stale_formula_edges(tmp_path: Path) -> None:
    store = _hub_corpus_store(tmp_path)
    store.upsert_record(
        _record("r_backup", "Weekly backup runs through jfcrypt", entities=["nov 2026", "jfcrypt"])
    )
    store.upsert_record(
        _record("r_search", "Search uses the exa provider now", entities=["nov 2026", "exa"])
    )
    store.upsert_record(
        _record(
            "r_key",
            "Backup key fingerprint verified intact",
            entities=["nov 2026", "jfcrypt", "fingerprint"],
        )
    )
    # Simulate an inflated hub edge left over by the old formula/reinforcement.
    store.upsert_association_edge("r_backup", "r_search", strength=1.0, edge_type="entity_overlap")
    assert any(edge.memory_id_b == "r_search" for edge in store.list_association_edges("r_backup"))

    result = store.rebuild_association_edges()

    assert result["records"] == 11
    assert result["edges"] >= 1
    backup_neighbors = {edge.memory_id_b for edge in store.list_association_edges("r_backup")}
    assert "r_search" not in backup_neighbors, (
        "rebuild must drop edges the current scoring rules no longer justify"
    )
    assert "r_key" in backup_neighbors, "rebuild must recreate justified edges"
