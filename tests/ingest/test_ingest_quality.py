from __future__ import annotations

from continuity.ingest.models import CandidateRecord, SourceRef
from continuity.ingest.quality import CandidateQualityGate


def _candidate(**overrides) -> CandidateRecord:
    values = {
        "candidate_id": "cand_quality",
        "kind": "project_convention",
        "title": "Do not store resident personal data in public notes",
        "summary": "Resident phone numbers and gate codes must not be stored in public orchard notes.",
        "tags": ["privacy"],
        "entities": ["resident data"],
        "confidence": 0.86,
        "importance": 0.78,
        "source_refs": [SourceRef(type="file", uri="file://docs/privacy.md")],
    }
    values.update(overrides)
    return CandidateRecord(**values)


def test_quality_gate_accepts_specific_candidate() -> None:
    result = CandidateQualityGate().apply(_candidate())

    assert isinstance(result, CandidateRecord)
    assert "quality" not in result.ingestion


def test_quality_gate_rejects_weak_procedure_existence_claim() -> None:
    result = CandidateQualityGate().apply(
        _candidate(
            kind="procedure_candidate",
            title="Harvest Day",
            summary="A procedure named Harvest Day exists in the civic orchard project.",
        )
    )

    assert not isinstance(result, CandidateRecord)
    assert "quality_gate_rejected" in result.reasons
    assert "weak_procedure" in result.reasons


def test_quality_gate_warns_and_lowers_confidence_for_generic_title() -> None:
    result = CandidateQualityGate().apply(
        _candidate(
            title="Public logs",
            summary="Public logs may include site names, tree varieties, harvest weights, and organization-level donation destinations.",
        )
    )

    assert isinstance(result, CandidateRecord)
    assert result.confidence == 0.74
    assert result.ingestion["quality"]["warnings"] == ["generic_title"]


def test_quality_gate_rejects_too_short_low_information_candidate() -> None:
    result = CandidateQualityGate().apply(
        _candidate(title="Notes", summary="A note exists.", tags=[], entities=[])
    )

    assert not isinstance(result, CandidateRecord)
    assert "too_short_summary" in result.reasons
    assert "low_information_candidate" in result.reasons


def test_quality_gate_warns_and_lowers_confidence_for_sparse_metadata_even_with_long_summary() -> (
    None
):
    result = CandidateQualityGate().apply(
        _candidate(
            title="Deployment behavior",
            summary="The deployment process restarts the service, verifies logs, checks health endpoints, and records any rollback decision in the release notes.",
            tags=[],
            entities=[],
            confidence=0.86,
        )
    )

    assert isinstance(result, CandidateRecord)
    assert result.confidence <= 0.74
    assert "sparse_metadata" in result.ingestion["quality"]["warnings"]
