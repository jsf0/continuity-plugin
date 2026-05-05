from __future__ import annotations

import json
import shutil
from pathlib import Path

from continuity.ingest.importer import ContinuityImporter
from continuity.ingest.jsonl import read_jsonl, write_jsonl
from continuity.ingest.models import CandidateRecord, SourceDocument, SourceRef
from continuity.ingest.refresh import RefreshPlanner, write_refresh_artifacts
from continuity.store import ContinuityStore

FIXTURE_ROOT = Path("tests/fixtures/ingestion/simple_docs")


def _copy_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    shutil.copytree(FIXTURE_ROOT, root)
    return root


def _candidate(uri: str = "file://README.md") -> CandidateRecord:
    return CandidateRecord(
        candidate_id="cand_refresh",
        kind="artifact_summary",
        title="Project capsule: refresh fixture",
        summary="The refresh fixture stores source-linked records.",
        tags=["project-capsule"],
        entities=["refresh fixture"],
        confidence=0.9,
        importance=0.8,
        source_refs=[SourceRef(type="file", uri=uri, segment_id=f"{uri}#simple-corpus")],
    )


def test_refresh_planner_detects_added_changed_removed_and_unchanged_sources(tmp_path) -> None:
    root = _copy_fixture(tmp_path)
    planner = RefreshPlanner()
    previous = planner.discover_current(root, include=["**/*.md"])
    previous_inventory = tmp_path / "previous.jsonl"
    write_jsonl(previous_inventory, [document.to_dict() for document in previous])

    (root / "README.md").write_text("# Simple Corpus\n\nChanged text.\n", encoding="utf-8")
    (root / "docs" / "release.md").unlink()
    (root / "docs" / "new.md").write_text("# New\n\nA new source.\n", encoding="utf-8")
    current = planner.discover_current(root, include=["**/*.md"])

    plan = planner.plan_from_inventory(
        previous_inventory_path=previous_inventory,
        current_documents=current,
    )

    assert any(document.source_id == "file://README.md" for document in plan.changed)
    assert any(document.source_id == "file://docs/release.md" for document in plan.removed)
    assert any(document.source_id == "file://docs/new.md" for document in plan.added)
    assert any(document.source_id == "file://docs/architecture.md" for document in plan.unchanged)


def test_write_refresh_artifacts_writes_reports(tmp_path) -> None:
    root = _copy_fixture(tmp_path)
    planner = RefreshPlanner()
    previous = planner.discover_current(root, include=["README.md"])
    previous_inventory = tmp_path / "previous.jsonl"
    output_dir = tmp_path / "refresh"
    write_jsonl(previous_inventory, [document.to_dict() for document in previous])
    (root / "README.md").write_text("# Simple Corpus\n\nChanged text.\n", encoding="utf-8")
    current = planner.discover_current(root, include=["README.md"])

    plan = planner.plan_from_inventory(
        previous_inventory_path=previous_inventory,
        current_documents=current,
    )
    write_refresh_artifacts(output_dir, current_documents=current, plan=plan)

    report = json.loads((output_dir / "refresh-report.json").read_text(encoding="utf-8"))
    assert report["changed_count"] == 1
    assert read_jsonl(output_dir / "changed-sources.jsonl")[0]["source_id"] == "file://README.md"
    assert "# Ingestion Refresh Report" in (output_dir / "refresh-report.md").read_text(
        encoding="utf-8"
    )


def test_refresh_apply_archives_stale_corpus_records(tmp_path) -> None:
    root = _copy_fixture(tmp_path)
    planner = RefreshPlanner()
    previous = planner.discover_current(root, include=["README.md"])
    previous_inventory = tmp_path / "previous.jsonl"
    db_path = tmp_path / "continuity.db"
    write_jsonl(previous_inventory, [document.to_dict() for document in previous])
    store = ContinuityStore(db_path)
    ContinuityImporter(store).import_records([_candidate()], dry_run=False)
    record = store.list_records()[0]
    assert record.status == "active"

    (root / "README.md").write_text("# Simple Corpus\n\nChanged text.\n", encoding="utf-8")
    current = planner.discover_current(root, include=["README.md"])
    plan = planner.plan_from_inventory(
        previous_inventory_path=previous_inventory,
        current_documents=current,
        store=store,
        apply=True,
    )

    assert plan.stale_record_ids == [record.id]
    assert plan.archived_record_ids == [record.id]
    assert store.get_record(record.id).status == "archived"  # type: ignore[union-attr]


def test_refresh_ignores_non_corpus_records_when_archiving(tmp_path) -> None:
    previous = [
        SourceDocument(
            source_id="file://README.md",
            source_type="markdown",
            uri="file://README.md",
            metadata={"sha256": "old"},
        )
    ]
    current = [
        SourceDocument(
            source_id="file://README.md",
            source_type="markdown",
            uri="file://README.md",
            metadata={"sha256": "new"},
        )
    ]
    store = ContinuityStore(tmp_path / "continuity.db")
    candidate = CandidateRecord.from_dict(
        {**_candidate().to_dict(), "trust_level": "session_extracted"}
    )
    ContinuityImporter(store).import_records([candidate], dry_run=False)

    plan = RefreshPlanner().plan(
        previous_documents=previous,
        current_documents=current,
        store=store,
        apply=True,
    )

    assert plan.stale_record_ids == []
    assert store.list_records()[0].status == "active"
