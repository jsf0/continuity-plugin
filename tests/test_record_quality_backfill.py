from __future__ import annotations

from continuity.models import ContextRecord
from continuity.quality_backfill import apply_quality_backfill, build_quality_backfill_report
from continuity.store import ContinuityStore


def test_quality_backfill_report_detects_recomputed_quality_drift(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        ContextRecord.from_dict(
            {
                "id": "r_generic_pre_quality",
                "kind": "environment_fact",
                "title": "Hermes global memory",
                "summary": "Continuity memory provider loaded from the plugin path.",
                "tags": ["environment_fact"],
                "entities": [],
                "confidence": 0.9,
                "importance": 0.7,
                "trust_level": "built_in_memory_mirror",
                "created_at": "2026-05-01T00:00:00Z",
                "updated_at": "2026-05-01T00:00:00Z",
                "quality": {},
            }
        ),
        create_associations=False,
    )

    report = build_quality_backfill_report(store)

    assert report.record_count == 1
    assert report.drift_count == 1
    assert report.updated_count == 0
    assert report.records[0]["id"] == "r_generic_pre_quality"
    assert report.records[0]["persisted_warnings"] == []
    assert "generic_title" in report.records[0]["recomputed_warnings"]
    assert "quality_differs" in report.records[0]["reasons"]


def test_quality_backfill_apply_updates_only_quality_metadata(tmp_path):
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    original = ContextRecord.from_dict(
        {
            "id": "r_sparse_corpus",
            "kind": "lesson_learned",
            "title": "Notes",
            "summary": "Use documented retry behavior when the worker queue stalls.",
            "details": "Keep this detail out of retrieval-noise quality diagnostics.",
            "tags": [],
            "entities": [],
            "confidence": 0.8,
            "importance": 0.6,
            "trust_level": "corpus_distilled",
            "created_at": "2026-05-01T00:00:00Z",
            "updated_at": "2026-05-01T00:00:00Z",
            "quality": {},
        }
    )
    store.upsert_record(original, create_associations=False)

    report = apply_quality_backfill(store)

    updated = store.get_record("r_sparse_corpus")
    assert updated is not None
    assert report.updated_count == 1
    assert updated.details == original.details
    assert updated.tags == original.tags
    assert updated.entities == original.entities
    assert updated.embedding_text == original.embedding_text
    assert updated.updated_at != original.updated_at
    assert "generic_title" in updated.quality["warnings"]
    assert "missing_source_ref" in updated.quality["warnings"]
    assert updated.quality["review_required"] is True
