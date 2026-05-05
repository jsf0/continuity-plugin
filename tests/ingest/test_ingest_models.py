from __future__ import annotations

import pytest

from continuity.ingest.models import (
    CandidateRecord,
    IngestionRunManifest,
    ParsedBlock,
    ParsedDocument,
    ReviewDecision,
    SourceDocument,
    SourceLocation,
    SourceRef,
    SourceSegment,
    stable_hash,
    stable_id,
)


def test_source_document_round_trips_with_metadata_and_scope() -> None:
    document = SourceDocument(
        source_id="file:///repo/docs/architecture.md",
        source_type="markdown",
        uri="file:///repo/docs/architecture.md",
        title="Architecture",
        collection="continuity",
        metadata={"sha256": "abc", "size_bytes": 123},
        scope_project="continuity-memory",
        scope_repo="/repo",
    )

    restored = SourceDocument.from_dict(document.to_dict())

    assert restored == document
    assert restored.metadata["sha256"] == "abc"
    assert restored.scope_project == "continuity-memory"


def test_candidate_record_requires_source_ref_for_corpus_distilled_records() -> None:
    with pytest.raises(ValueError, match="source_refs"):
        CandidateRecord(
            candidate_id="cand_missing_source",
            kind="project_convention",
            title="Compact records",
            summary="Continuity records should stay compact.",
            trust_level="corpus_distilled",
            source_refs=[],
        )


def test_candidate_record_round_trips_with_source_refs_and_ingestion_metadata() -> None:
    source_ref = SourceRef(
        type="file",
        uri="file:///repo/docs/architecture.md",
        path="/repo/docs/architecture.md",
        segment_id="file:///repo/docs/architecture.md#retrieval-model",
        section="Retrieval model",
        line_start=38,
        line_end=92,
        content_hash="abc123",
    )
    candidate = CandidateRecord(
        candidate_id="cand_001",
        kind="project_convention",
        title="Continuity records should be compact",
        summary="Corpus ingestion should produce compact source-linked records.",
        details="Derived from the retrieval model section.",
        scope_project="continuity-memory",
        scope_repo="/repo",
        tags=["retrieval", "source-refs"],
        entities=["Continuity Memory"],
        confidence=0.88,
        importance=0.8,
        trust_level="corpus_distilled",
        source_refs=[source_ref],
        ingestion={"run_id": "run-1", "extractor": "deterministic"},
        review={"status": "pending_review"},
    )

    restored = CandidateRecord.from_dict(candidate.to_dict())

    assert restored == candidate
    assert restored.source_refs[0].line_start == 38
    assert restored.ingestion["run_id"] == "run-1"


def test_candidate_record_validates_probability_fields() -> None:
    source_ref = SourceRef(type="file", uri="file:///repo/README.md")

    with pytest.raises(ValueError, match="confidence"):
        CandidateRecord(
            candidate_id="cand_bad_confidence",
            kind="artifact_summary",
            title="Project summary",
            summary="A useful project summary.",
            confidence=1.5,
            source_refs=[source_ref],
        )


def test_segment_round_trips_with_location_and_metadata() -> None:
    segment = SourceSegment(
        segment_id="file:///repo/docs/architecture.md#intro",
        source_id="file:///repo/docs/architecture.md",
        kind="section",
        title="Intro",
        text="Continuity stores compact records.",
        location=SourceLocation(
            uri="file:///repo/docs/architecture.md",
            path="/repo/docs/architecture.md",
            line_start=1,
            line_end=5,
        ),
        metadata={"heading_path": ["Intro"], "content_hash": "abc"},
        scope_project="continuity-memory",
    )

    restored = SourceSegment.from_dict(segment.to_dict())

    assert restored == segment
    assert restored.location.line_end == 5
    assert restored.metadata["heading_path"] == ["Intro"]


def test_parsed_document_round_trips_blocks() -> None:
    parsed = ParsedDocument(
        source_id="file:///repo/README.md",
        source_type="markdown",
        title="README",
        text="# README\nBody",
        blocks=[
            ParsedBlock(
                block_id="b1",
                kind="heading",
                text="README",
                level=1,
                location=SourceLocation(uri="file:///repo/README.md", line_start=1, line_end=1),
            )
        ],
        metadata={"parser": "markdown"},
    )

    restored = ParsedDocument.from_dict(parsed.to_dict())

    assert restored == parsed
    assert restored.blocks[0].kind == "heading"


def test_manifest_and_review_decision_round_trip() -> None:
    manifest = IngestionRunManifest(
        run_id="run-1",
        created_at="2026-05-05T15:00:00Z",
        recipe="docs",
        input_roots=["/repo/docs"],
        config_hash="hash",
        source_count=2,
        segment_count=4,
        candidate_count=3,
        approved_count=1,
        imported_count=0,
        rejected_count=1,
        output_dir=".ingestion/run-1",
    )
    decision = ReviewDecision(
        candidate_id="cand_001",
        status="approved",
        reasons=["high confidence"],
    )

    assert IngestionRunManifest.from_dict(manifest.to_dict()) == manifest
    assert ReviewDecision.from_dict(decision.to_dict()) == decision


def test_stable_hash_and_id_are_deterministic() -> None:
    assert stable_hash({"b": 2, "a": 1}) == stable_hash({"a": 1, "b": 2})
    assert stable_id("corpus", "source", "title") == stable_id("corpus", "source", "title")
    assert stable_id("corpus", "source", "title").startswith("ing_")
