from __future__ import annotations

import json
from pathlib import Path

from continuity.ingest.jsonl import read_jsonl
from continuity.ingest.pipeline import IngestionPipeline, run_dry_inventory_and_segment

FIXTURE_ROOT = Path("tests/fixtures/ingestion/simple_docs")


def test_pipeline_writes_manifest_inventory_segments_and_report(tmp_path) -> None:
    output_dir = tmp_path / "run-1"

    result = IngestionPipeline().run_dry_inventory_and_segment(
        roots=[FIXTURE_ROOT],
        output_dir=output_dir,
        recipe="docs",
        run_id="run-1",
        created_at="2026-05-05T15:00:00Z",
        include=["**/*.md"],
        exclude=["**/noisy.md"],
        project="continuity-ingestion-fixture",
        repo=str(FIXTURE_ROOT),
        collection="simple-docs",
    )

    manifest_path = output_dir / "manifest.json"
    inventory_path = output_dir / "inventory.jsonl"
    segments_path = output_dir / "segments.jsonl"
    candidates_path = output_dir / "candidate-records.jsonl"
    merged_path = output_dir / "merged-records.jsonl"
    approved_path = output_dir / "approved-records.jsonl"
    pending_path = output_dir / "pending-records.jsonl"
    rejected_path = output_dir / "rejected-candidates.jsonl"
    evals_path = output_dir / "retrieval-evals.jsonl"
    review_path = output_dir / "review.md"
    report_path = output_dir / "import-report.md"

    assert result.manifest.run_id == "run-1"
    assert manifest_path.exists()
    assert inventory_path.exists()
    assert segments_path.exists()
    assert candidates_path.exists()
    assert merged_path.exists()
    assert approved_path.exists()
    assert pending_path.exists()
    assert rejected_path.exists()
    assert evals_path.exists()
    assert review_path.exists()
    assert report_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    inventory = read_jsonl(inventory_path)
    segments = read_jsonl(segments_path)
    report = report_path.read_text(encoding="utf-8")
    candidates = read_jsonl(candidates_path)
    merged = read_jsonl(merged_path)
    approved = read_jsonl(approved_path)
    pending = read_jsonl(pending_path)

    assert manifest["run_id"] == "run-1"
    assert manifest["recipe"] == "docs"
    assert manifest["source_count"] == 5
    assert manifest["segment_count"] == len(segments)
    assert len(inventory) == 5
    assert manifest["candidate_count"] == len(candidates)
    assert manifest["approved_count"] == len(approved)
    assert candidates
    assert merged
    assert len(pending) + len(approved) == len(merged)
    assert any(row["kind"] == "artifact_summary" for row in candidates)
    assert any(row["kind"] == "procedure_candidate" for row in candidates)
    assert any(row["source_id"] == "file://docs/architecture.md" for row in inventory)
    assert any(
        row["segment_id"] == "file://docs/architecture.md#retrieval-model" for row in segments
    )
    assert "# Ingestion Dry Run Report" in report
    assert "Sources discovered: 5" in report
    assert "Segments generated:" in report
    assert "Candidate extraction" in report


def test_pipeline_function_uses_default_output_directory_shape(tmp_path) -> None:
    output_dir = tmp_path / ".ingestion" / "run-2"

    result = run_dry_inventory_and_segment(
        roots=[FIXTURE_ROOT],
        output_dir=output_dir,
        recipe="docs",
        run_id="run-2",
        created_at="2026-05-05T16:00:00Z",
        include=["README.md"],
    )

    assert result.output_dir == output_dir
    assert result.manifest.source_count == 1
    assert (output_dir / "manifest.json").exists()
    assert read_jsonl(output_dir / "inventory.jsonl")[0]["source_id"] == "file://README.md"


def test_pipeline_skips_binary_sources_by_default(tmp_path) -> None:
    output_dir = tmp_path / "run-binary"

    result = IngestionPipeline().run_dry_inventory_and_segment(
        roots=[FIXTURE_ROOT],
        output_dir=output_dir,
        recipe="docs",
        run_id="run-binary",
        created_at="2026-05-05T17:00:00Z",
        include=["**/*"],
    )

    inventory = read_jsonl(output_dir / "inventory.jsonl")

    assert result.manifest.source_count == len(inventory)
    assert all(row["source_type"] != "binary" for row in inventory)
    assert all("ignored.bin" not in row["uri"] for row in inventory)


def test_pipeline_safe_auto_generates_evals_for_approved_records(tmp_path) -> None:
    output_dir = tmp_path / "run-evals"

    result = IngestionPipeline().run_dry_inventory_and_segment(
        roots=[FIXTURE_ROOT],
        output_dir=output_dir,
        recipe="docs",
        run_id="run-evals",
        created_at="2026-05-05T18:00:00Z",
        include=["README.md"],
        project="continuity-ingestion-fixture",
        review_policy="safe-auto",
    )

    approved = read_jsonl(output_dir / "approved-records.jsonl")
    evals = read_jsonl(output_dir / "retrieval-evals.jsonl")

    assert result.manifest.approved_count == 1
    assert approved[0]["title"] == "Project capsule: continuity-ingestion-fixture"
    assert evals[0]["expected_record_titles"] == [approved[0]["title"]]
