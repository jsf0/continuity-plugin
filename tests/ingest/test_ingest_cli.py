from __future__ import annotations

import json
from pathlib import Path

from continuity.ingest.cli import main
from continuity.ingest.jsonl import read_jsonl, write_jsonl
from continuity.ingest.models import CandidateRecord, SourceRef
from continuity.store import ContinuityStore

FIXTURE_ROOT = Path("tests/fixtures/ingestion/simple_docs")


def _candidate() -> CandidateRecord:
    return CandidateRecord(
        candidate_id="cand_cli",
        kind="artifact_summary",
        title="Project capsule: CLI fixture",
        summary="The CLI fixture stores compact source-linked records.",
        tags=["project-capsule"],
        entities=["CLI Fixture"],
        confidence=0.9,
        importance=0.8,
        source_refs=[
            SourceRef(type="file", uri="file://README.md", segment_id="file://README.md#readme")
        ],
    )


def test_cli_inventory_writes_inventory_jsonl(tmp_path) -> None:
    output = tmp_path / "inventory.jsonl"

    exit_code = main(
        [
            "inventory",
            str(FIXTURE_ROOT),
            "--include",
            "README.md",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    rows = read_jsonl(output)
    assert len(rows) == 1
    assert rows[0]["source_id"] == "file://README.md"


def test_cli_segment_writes_segments_from_inventory(tmp_path) -> None:
    inventory = tmp_path / "inventory.jsonl"
    segments = tmp_path / "segments.jsonl"
    main(["inventory", str(FIXTURE_ROOT), "--include", "README.md", "--output", str(inventory)])

    exit_code = main(["segment", str(inventory), "--output", str(segments)])

    assert exit_code == 0
    rows = read_jsonl(segments)
    assert rows[0]["segment_id"] == "file://README.md#simple-corpus"


def test_cli_run_writes_dry_run_artifacts(tmp_path) -> None:
    output_dir = tmp_path / "run"

    exit_code = main(
        [
            "run",
            str(FIXTURE_ROOT),
            "--recipe",
            "docs",
            "--run-id",
            "cli-run",
            "--created-at",
            "2026-05-05T18:00:00Z",
            "--include",
            "README.md",
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == "cli-run"
    assert manifest["source_count"] == 1
    assert (output_dir / "segments.jsonl").exists()
    assert (output_dir / "import-report.md").exists()


def test_cli_review_splits_candidate_records(tmp_path) -> None:
    candidates_path = tmp_path / "candidate-records.jsonl"
    output_dir = tmp_path / "review"
    write_jsonl(candidates_path, [_candidate().to_dict()])

    exit_code = main(
        [
            "review",
            str(candidates_path),
            "--policy",
            "conservative",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert read_jsonl(output_dir / "approved-records.jsonl")[0]["candidate_id"] == "cand_cli"
    assert (output_dir / "review.md").exists()


def test_cli_import_defaults_to_dry_run_and_apply_writes_records(tmp_path) -> None:
    candidates_path = tmp_path / "approved-records.jsonl"
    db_path = tmp_path / "continuity.db"
    write_jsonl(candidates_path, [_candidate().to_dict()])

    dry_run_exit = main(["import", str(candidates_path), "--db-path", str(db_path)])
    apply_exit = main(["import", str(candidates_path), "--db-path", str(db_path), "--apply"])

    assert dry_run_exit == 0
    assert apply_exit == 0
    store = ContinuityStore(db_path)
    assert store.count_records() == 1
    assert store.fts_search("fixture", limit=5)


def test_cli_eval_runs_retrieval_eval_file(tmp_path) -> None:
    candidates_path = tmp_path / "approved-records.jsonl"
    evals_path = tmp_path / "retrieval-evals.jsonl"
    report_path = tmp_path / "eval-report.jsonl"
    db_path = tmp_path / "continuity.db"
    candidate = _candidate()
    write_jsonl(candidates_path, [candidate.to_dict()])
    main(["import", str(candidates_path), "--db-path", str(db_path), "--apply"])
    write_jsonl(
        evals_path,
        [
            {
                "eval_id": "eval_cli",
                "query": "What should I know about CLI fixture?",
                "expected_record_titles": [candidate.title],
                "expected_tags": ["project-capsule"],
                "forbidden_tags": ["unrelated-noise"],
            }
        ],
    )

    exit_code = main(
        [
            "eval",
            str(evals_path),
            "--db-path",
            str(db_path),
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 0
    assert read_jsonl(report_path)[0]["passed"] is True
