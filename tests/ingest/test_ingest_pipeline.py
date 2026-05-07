from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

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


def test_pipeline_propagates_run_context_labels_to_artifacts_and_evals(tmp_path) -> None:
    output_dir = tmp_path / "run-context"

    result = IngestionPipeline().run_dry_inventory_and_segment(
        roots=[FIXTURE_ROOT],
        output_dir=output_dir,
        recipe="docs",
        run_id="run-context",
        created_at="2026-05-06T20:00:00Z",
        include=["README.md"],
        project="continuity-ingestion-fixture",
        review_policy="safe-auto",
        context={
            "labels": {"customer": "Acme"},
            "partition_keys": ["customer"],
            "identity_keys": ["project"],
            "collision_risk": "high",
        },
    )

    inventory = read_jsonl(output_dir / "inventory.jsonl")
    segments = read_jsonl(output_dir / "segments.jsonl")
    candidates = read_jsonl(output_dir / "candidate-records.jsonl")
    evals = read_jsonl(output_dir / "retrieval-evals.jsonl")
    stats = json.loads((output_dir / "ingestion-stats.json").read_text(encoding="utf-8"))
    expected_context = {
        "labels": {"customer": "acme"},
        "partition_keys": ["customer"],
        "soft_keys": [],
        "identity_keys": [],
        "collision_risk": "high",
    }

    assert result.manifest.approved_count == 1
    assert inventory[0]["metadata"]["context"] == expected_context
    assert segments[0]["metadata"]["context"] == expected_context
    assert candidates[0]["ingestion"]["context"] == expected_context
    assert evals[0]["query_context"] == expected_context
    assert stats["context"]["documents_with_labels"] == 1
    assert stats["context"]["candidates_with_labels"] == 1
    assert stats["context"]["by_partition_key"] == {"customer": 1}


def test_pipeline_preserves_context_on_candidate_source_refs(tmp_path) -> None:
    output_dir = tmp_path / "run-source-ref-context"

    IngestionPipeline().run_dry_inventory_and_segment(
        roots=[FIXTURE_ROOT],
        output_dir=output_dir,
        recipe="docs",
        run_id="run-source-ref-context",
        created_at="2026-05-06T21:00:00Z",
        include=["README.md"],
        project="continuity-ingestion-fixture",
        context={
            "labels": {"customer": "acme"},
            "partition_keys": ["customer"],
            "collision_risk": "high",
        },
    )

    candidates = read_jsonl(output_dir / "candidate-records.jsonl")

    assert candidates[0]["source_refs"][0]["metadata"]["context"]["labels"] == {"customer": "acme"}


@pytest.mark.skipif(
    shutil.which("groff") is None or shutil.which("col") is None, reason="groff/col not installed"
)
def test_pipeline_ingests_raw_manpage_sources(tmp_path) -> None:
    corpus = tmp_path / "manpages"
    corpus.mkdir()
    (corpus / "ifconfig.8").write_text(
        ".Dd May 6, 2026\n"
        ".Dt IFCONFIG 8\n"
        ".Os\n"
        ".Sh NAME\n"
        ".Nm ifconfig\n"
        ".Nd configure network interface parameters\n"
        ".Sh SYNOPSIS\n"
        ".Nm ifconfig\n"
        ".Ar interface alias address\n"
        ".Sh DESCRIPTION\n"
        ".Nm\n"
        "configures network interface parameters.\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "run-manpage"

    result = IngestionPipeline().run_dry_inventory_and_segment(
        roots=[corpus],
        output_dir=output_dir,
        recipe="manpage",
        include=["*.8"],
        context={"labels": {"os": "openbsd"}, "partition_keys": ["os"], "collision_risk": "high"},
    )

    inventory = read_jsonl(output_dir / "inventory.jsonl")
    segments = read_jsonl(output_dir / "segments.jsonl")
    candidates = read_jsonl(output_dir / "candidate-records.jsonl")
    assert result.manifest.source_count == 1
    assert inventory[0]["source_type"] == "manpage"
    assert {segment["title"] for segment in segments} >= {"NAME", "SYNOPSIS", "DESCRIPTION"}
    assert {candidate["title"] for candidate in candidates} >= {
        "Manpage NAME: ifconfig",
        "Manpage SYNOPSIS: ifconfig",
    }
    assert segments[0]["metadata"]["context"] == {
        "labels": {"os": "openbsd", "command": "ifconfig", "manual_section": "8"},
        "partition_keys": ["os"],
        "soft_keys": [],
        "identity_keys": ["command", "manual_section"],
        "collision_risk": "high",
    }
    assert candidates[0]["ingestion"]["context"] == segments[0]["metadata"]["context"]
