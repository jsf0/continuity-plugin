from __future__ import annotations

from continuity.ingest.importer import ContinuityImporter, ImportResult, candidate_to_context_record
from continuity.ingest.models import CandidateRecord, SourceRef
from continuity.store import ContinuityStore


def _candidate(candidate_id: str = "cand_001") -> CandidateRecord:
    return CandidateRecord(
        candidate_id=candidate_id,
        kind="codebase_fact",
        title="Test command: uv run pytest tests/ -q",
        summary="The corpus documents `uv run pytest tests/ -q` as a test command for this project.",
        details="Extracted from README.md.",
        scope_project="continuity-ingestion-fixture",
        scope_repo="/repo",
        tags=["codebase-map", "test-command"],
        entities=["uv run pytest tests/ -q"],
        confidence=0.78,
        importance=0.68,
        trust_level="corpus_distilled",
        source_refs=[
            SourceRef(
                type="file",
                uri="file://README.md",
                path="README.md",
                segment_id="file://README.md#testing",
                section="Testing",
                line_start=3,
                line_end=6,
                content_hash="abc123",
            )
        ],
        ingestion={"extractor": "code-or-config-fact"},
    )


def test_candidate_to_context_record_preserves_core_fields_and_source_refs() -> None:
    candidate = _candidate()

    record = candidate_to_context_record(candidate)

    assert record.id.startswith("ing_")
    assert record.kind == "codebase_fact"
    assert record.title == candidate.title
    assert record.summary == candidate.summary
    assert record.details == candidate.details
    assert record.scope_project == candidate.scope_project
    assert record.scope_repo == candidate.scope_repo
    assert record.tags == candidate.tags
    assert set(candidate.entities) <= set(record.entities)
    assert "Extracted" in record.entities
    assert record.confidence == candidate.confidence
    assert record.importance == candidate.importance
    assert record.trust_level == "corpus_distilled"
    assert record.source_hash
    assert record.sources[0].type == "file"
    assert record.sources[0].id == "file://README.md#testing"
    assert record.sources[0].uri == "file://README.md"
    assert record.sources[0].range == "lines 3-6"
    assert record.sources[0].label == "Testing"


def test_importer_dry_run_does_not_write_records(tmp_path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    importer = ContinuityImporter(store)

    result = importer.import_records([_candidate()], dry_run=True)

    assert isinstance(result, ImportResult)
    assert result.dry_run is True
    assert result.created == []
    assert result.updated == []
    assert result.skipped == ["cand_001"]
    assert store.count_records() == 0


def test_importer_writes_records_to_store_and_fts(tmp_path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    importer = ContinuityImporter(store)
    candidate = _candidate()

    result = importer.import_records([candidate], dry_run=False)

    assert result.dry_run is False
    assert len(result.created) == 1
    assert result.updated == []
    assert result.failed == []
    record = store.get_record(result.created[0])
    assert record is not None
    assert record.title == candidate.title
    assert record.trust_level == "corpus_distilled"
    assert store.fts_search("pytest", limit=5)[0].record.id == record.id


def test_importer_is_idempotent_and_updates_existing_record(tmp_path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    importer = ContinuityImporter(store)
    candidate = _candidate()
    first = importer.import_records([candidate], dry_run=False)
    changed = CandidateRecord.from_dict(
        {**candidate.to_dict(), "summary": "Updated pytest command summary."}
    )

    second = importer.import_records([changed], dry_run=False)

    assert store.count_records() == 1
    assert first.created == second.updated
    record = store.get_record(first.created[0])
    assert record is not None
    assert record.summary == "Updated pytest command summary."


def test_candidate_to_context_record_preserves_ingestion_context_labels() -> None:
    candidate = CandidateRecord.from_dict(
        {
            **_candidate().to_dict(),
            "ingestion": {
                "extractor": "code-or-config-fact",
                "context": {
                    "labels": {"os": "OpenBSD", "command": "ifconfig"},
                    "partition_keys": ["os"],
                    "identity_keys": ["command"],
                    "collision_risk": "high",
                },
            },
        }
    )

    record = candidate_to_context_record(candidate)

    assert record.quality["context"] == {
        "labels": {"command": "ifconfig", "os": "openbsd"},
        "partition_keys": ["os"],
        "soft_keys": [],
        "identity_keys": ["command"],
        "collision_risk": "high",
    }


def test_candidate_context_contributes_to_source_hash() -> None:
    base = _candidate().to_dict()
    openbsd = CandidateRecord.from_dict(
        {
            **base,
            "ingestion": {
                "context": {
                    "labels": {"os": "openbsd"},
                    "partition_keys": ["os"],
                    "collision_risk": "high",
                }
            },
        }
    )
    linux = CandidateRecord.from_dict(
        {
            **base,
            "ingestion": {
                "context": {
                    "labels": {"os": "linux"},
                    "partition_keys": ["os"],
                    "collision_risk": "high",
                }
            },
        }
    )

    assert (
        candidate_to_context_record(openbsd).source_hash
        != candidate_to_context_record(linux).source_hash
    )
