from __future__ import annotations

import pytest

from continuity.models import ContextRecord, SourceRef


def test_source_ref_round_trips_dict() -> None:
    source = SourceRef(
        type="session",
        id="session-1",
        uri=None,
        range="turns 1-3",
        label="debugging",
        created_at="2026-05-02T00:00:00Z",
    )

    assert SourceRef.from_dict(source.to_dict()) == source


def test_context_record_round_trips_dict_with_defaults() -> None:
    record = ContextRecord.new(
        id="r1",
        kind="lesson_learned",
        title="Delegate timeout",
        summary="delegate_task can timeout before child API calls.",
        scope_project="guard-proxy",
        tags=["delegate_task", "timeout"],
        entities=["api_calls:0"],
        sources=[SourceRef(type="session", id="s1", range="turns 1-2")],
        confidence=0.9,
        importance=0.8,
    )

    restored = ContextRecord.from_dict(record.to_dict())

    assert restored == record
    assert restored.trust_level == "session_extracted"
    assert "kind: lesson_learned" in restored.embedding_text
    assert "project: guard-proxy" in restored.embedding_text
    assert "title: Delegate timeout" in restored.embedding_text


@pytest.mark.parametrize("bad_kind", ["", "unknown", "LESSON_LEARNED"])
def test_context_record_rejects_invalid_kind(bad_kind: str) -> None:
    with pytest.raises(ValueError, match="kind"):
        ContextRecord.new(id="r1", kind=bad_kind, title="t", summary="s")


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_context_record_rejects_confidence_out_of_range(value: float) -> None:
    with pytest.raises(ValueError, match="confidence"):
        ContextRecord.new(
            id="r1",
            kind="lesson_learned",
            title="t",
            summary="s",
            confidence=value,
        )


def test_context_record_round_trips_quality_metadata_without_embedding_pollution() -> None:
    record = ContextRecord.new(
        id="r_quality_meta",
        kind="project_convention",
        title="Quality metadata test",
        summary="Quality metadata is stored separately from embedding text.",
        tags=["quality"],
        entities=["quality metadata"],
        trust_level="explicit_user",
        quality={"warnings": ["sparse_metadata"], "score": 0.76, "facets": ["software_project"]},
    )

    payload = record.to_dict()
    restored = ContextRecord.from_dict(payload)

    assert restored.quality == {
        "warnings": ["sparse_metadata"],
        "score": 0.76,
        "facets": ["software_project"],
    }
    assert "sparse_metadata" not in (restored.embedding_text or "")
