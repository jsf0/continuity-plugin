from __future__ import annotations

from continuity.ingest.dedupe import BasicDeduper, DedupeResult
from continuity.ingest.models import CandidateRecord, SourceRef


def _ref(uri: str = "file://README.md", segment_id: str = "file://README.md#intro") -> SourceRef:
    return SourceRef(type="file", uri=uri, segment_id=segment_id, line_start=1, line_end=3)


def _candidate(
    candidate_id: str,
    *,
    title: str = "Project capsule: demo",
    kind: str = "artifact_summary",
    scope_project: str = "demo",
    source_refs: list[SourceRef] | None = None,
    tags: list[str] | None = None,
    entities: list[str] | None = None,
    confidence: float = 0.7,
    importance: float = 0.7,
) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=candidate_id,
        kind=kind,
        title=title,
        summary=f"Summary for {title}.",
        scope_project=scope_project,
        tags=tags or ["project-capsule"],
        entities=entities or ["Demo"],
        confidence=confidence,
        importance=importance,
        source_refs=source_refs or [_ref()],
    )


def test_basic_deduper_keeps_unique_candidates() -> None:
    candidates = [
        _candidate("cand_1", title="Project capsule: demo"),
        _candidate("cand_2", title="Procedure candidate: release", kind="procedure_candidate"),
    ]

    result = BasicDeduper().dedupe(candidates)

    assert isinstance(result, DedupeResult)
    assert result.accepted == candidates
    assert result.duplicates == []
    assert result.rejections == []


def test_basic_deduper_merges_duplicate_title_kind_and_scope() -> None:
    first = _candidate("cand_1", tags=["project-capsule"], entities=["Demo"], confidence=0.6)
    duplicate = _candidate(
        "cand_2",
        title=" project capsule: demo ",
        tags=["corpus-ingestion"],
        entities=["README"],
        confidence=0.9,
        source_refs=[_ref("file://README.md", "file://README.md#overview")],
    )

    result = BasicDeduper().dedupe([first, duplicate])

    assert len(result.accepted) == 1
    merged = result.accepted[0]
    assert merged.candidate_id == "cand_1"
    assert merged.confidence == 0.9
    assert merged.tags == ["project-capsule", "corpus-ingestion"]
    assert merged.entities == ["Demo", "README"]
    assert [ref.segment_id for ref in merged.source_refs] == [
        "file://README.md#intro",
        "file://README.md#overview",
    ]
    assert result.duplicates == [("cand_2", "cand_1")]
    assert result.rejections[0].item_id == "cand_2"
    assert "duplicate_candidate" in result.rejections[0].reasons


def test_basic_deduper_merges_duplicate_source_refs_even_with_different_title() -> None:
    first = _candidate("cand_1", title="Test command: pytest", kind="codebase_fact")
    duplicate = _candidate("cand_2", title="Pytest command", kind="codebase_fact")

    result = BasicDeduper().dedupe([first, duplicate])

    assert len(result.accepted) == 1
    assert result.duplicates == [("cand_2", "cand_1")]


def test_basic_deduper_does_not_merge_same_title_in_different_scope() -> None:
    first = _candidate("cand_1", scope_project="demo-a")
    second = _candidate("cand_2", scope_project="demo-b")

    result = BasicDeduper().dedupe([first, second])

    assert len(result.accepted) == 2
    assert result.duplicates == []
