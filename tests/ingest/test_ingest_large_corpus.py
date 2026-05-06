from __future__ import annotations

import json
from pathlib import Path

from continuity.ingest.jsonl import read_jsonl
from continuity.ingest.pipeline import IngestionPipeline

LARGE_ROOT = Path("tests/fixtures/ingestion/large_corpus")


def test_large_corpus_deterministic_pipeline_exercises_many_documents(tmp_path) -> None:
    output_dir = tmp_path / "large-det"

    result = IngestionPipeline().run_dry_inventory_and_segment(
        roots=[LARGE_ROOT],
        output_dir=output_dir,
        recipe="docs",
        run_id="large-det",
        created_at="2026-05-05T21:00:00Z",
        include=["**/*.md"],
        project="civic-orchard",
        review_policy="safe-auto",
    )

    candidates = read_jsonl(output_dir / "candidate-records.jsonl")
    approved = read_jsonl(output_dir / "approved-records.jsonl")
    pending = read_jsonl(output_dir / "pending-records.jsonl")
    evals = read_jsonl(output_dir / "retrieval-evals.jsonl")
    stats = json.loads((output_dir / "ingestion-stats.json").read_text(encoding="utf-8"))

    assert result.manifest.source_count == 21
    assert result.manifest.segment_count >= 40
    assert result.manifest.candidate_count == len(candidates)
    assert _titles(candidates) >= {
        "Project capsule: civic-orchard",
        "Procedure candidate: Spring launch checklist",
        "Procedure candidate: Harvest day checklist",
        "Procedure candidate: Safety incident workflow",
        "Test command: uv run pytest tests/ -q",
        "Lint command: uv run ruff check .",
    }
    assert {candidate["title"] for candidate in approved} >= {
        "Project capsule: civic-orchard",
        "Test command: uv run pytest tests/ -q",
    }
    assert any(candidate["kind"] == "procedure_candidate" for candidate in pending)
    assert len(evals) == len(approved)
    assert all(candidate["scope_project"] == "civic-orchard" for candidate in candidates)
    assert all(candidate["source_refs"] for candidate in candidates)
    assert stats["summary"]["source_count"] == result.manifest.source_count
    assert stats["summary"]["segment_count"] == result.manifest.segment_count
    assert stats["summary"]["candidate_count"] == len(candidates)
    assert stats["sources"]["by_type"] == {"markdown": 21}
    assert stats["segments"]["max_chars"] >= stats["segments"]["avg_chars"] > 0
    assert stats["segments"]["by_source_type"] == {"markdown": result.manifest.segment_count}
    assert stats["candidates"]["by_kind"]["procedure_candidate"] >= 3
    assert stats["review"]["approved_count"] == len(approved)
    assert stats["review"]["pending_count"] == len(pending)
    assert "by_reason" in stats["rejections"]


def _titles(rows: list[dict[str, object]]) -> set[str]:
    return {str(row["title"]) for row in rows}
