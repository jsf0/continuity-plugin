from __future__ import annotations

from pathlib import Path

from continuity.models import ContextRecord, SourceRef
from continuity.store import ContinuityStore


def make_record(record_id: str = "r1", summary: str = "delegate_task timeout") -> ContextRecord:
    return ContextRecord.new(
        id=record_id,
        kind="lesson_learned",
        scope_project="guard-proxy",
        title="Delegate timeout",
        summary=summary,
        tags=["delegate_task", "timeout"],
        entities=["api_calls:0"],
        sources=[SourceRef(type="session", id="s1", range="turns 1-2")],
        confidence=0.9,
        importance=0.8,
    )


def test_store_migrates_idempotently(tmp_path: Path) -> None:
    db_path = tmp_path / "continuity.db"
    store = ContinuityStore(db_path)

    store.migrate()
    store.migrate()

    assert db_path.exists()
    assert store.schema_versions() == [1, 2]


def test_upsert_get_list_and_delete_record(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    record = make_record()

    store.upsert_record(record)

    assert store.get_record("r1") == record
    assert store.count_records() == 1
    assert [r.id for r in store.list_records()] == ["r1"]

    store.delete_record("r1")

    assert store.get_record("r1") is None
    assert store.count_records() == 0


def test_upsert_replaces_existing_record_and_fts(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(make_record(summary="delegate_task timeout before API calls"))
    store.upsert_record(make_record(summary="cargo check is the authoritative verifier"))

    restored = store.get_record("r1")
    assert restored is not None
    assert restored.summary == "cargo check is the authoritative verifier"

    hits = store.fts_search("cargo", limit=5)
    assert [hit.record.id for hit in hits] == ["r1"]


def test_fts_search_finds_summary_tags_and_entities(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(make_record())

    assert [hit.record.id for hit in store.fts_search("delegate_task", limit=5)] == ["r1"]
    assert [hit.record.id for hit in store.fts_search("api_calls", limit=5)] == ["r1"]
    assert store.fts_search("llama-server", limit=5) == []
