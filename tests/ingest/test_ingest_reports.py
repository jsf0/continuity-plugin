from __future__ import annotations

from continuity.ingest.models import CandidateRecord, IngestionRunManifest, SourceRef
from continuity.ingest.reports import build_ingestion_stats


def _candidate(candidate_id: str, *, os_name: str) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=candidate_id,
        kind="codebase_fact",
        title="ifconfig alias syntax",
        summary=f"{os_name} ifconfig uses context-specific alias syntax.",
        tags=["ifconfig"],
        entities=["ifconfig"],
        source_refs=[SourceRef(type="file", uri=f"file://{os_name}/ifconfig.md")],
        ingestion={
            "context": {
                "labels": {"os": os_name, "command": "ifconfig"},
                "partition_keys": ["os"],
                "identity_keys": ["command"],
                "collision_risk": "high",
            }
        },
    )


def test_ingestion_stats_reports_high_collision_identity_conflicts() -> None:
    candidates = [_candidate("openbsd", os_name="openbsd"), _candidate("linux", os_name="linux")]

    stats = build_ingestion_stats(
        manifest=IngestionRunManifest(
            run_id="run-collisions",
            created_at="2026-05-06T22:00:00Z",
            recipe="docs",
            input_roots=["/tmp/corpus"],
            config_hash="abc123",
            candidate_count=len(candidates),
        ),
        documents=[],
        segments=[],
        candidates=candidates,
        merged_candidates=candidates,
        rejections=[],
        review_result=None,
    )

    assert stats["context"]["identity_partition_conflict_count"] == 1
    assert stats["context"]["identity_partition_conflicts"] == [
        {
            "identity": "command=ifconfig",
            "partition_key": "os",
            "partition_values": ["linux", "openbsd"],
            "candidate_count": 2,
            "titles": ["ifconfig alias syntax"],
        }
    ]
