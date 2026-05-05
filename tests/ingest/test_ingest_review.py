from __future__ import annotations

from continuity.ingest.jsonl import read_jsonl
from continuity.ingest.models import CandidateRecord, Rejection, SourceRef
from continuity.ingest.review import ReviewPolicy, ReviewResult, write_review_artifacts


def _ref() -> SourceRef:
    return SourceRef(type="file", uri="file://README.md", segment_id="file://README.md#intro")


def _candidate(
    candidate_id: str,
    *,
    kind: str = "artifact_summary",
    title: str = "Project capsule: demo",
    confidence: float = 0.8,
    importance: float = 0.7,
    trust_level: str = "corpus_distilled",
) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=candidate_id,
        kind=kind,
        title=title,
        summary="The project stores compact source-linked records.",
        tags=["project-capsule"],
        entities=["Demo"],
        confidence=confidence,
        importance=importance,
        trust_level=trust_level,
        source_refs=[_ref()],
        review={"status": "pending_review"},
    )


def test_review_policy_propose_marks_everything_pending() -> None:
    decision = ReviewPolicy("propose").decide(_candidate("cand_1"))

    assert decision.status == "pending_review"
    assert "propose_mode" in decision.reasons


def test_review_policy_require_review_marks_everything_pending() -> None:
    decision = ReviewPolicy("require-review").decide(_candidate("cand_1"))

    assert decision.status == "pending_review"
    assert "review_required" in decision.reasons


def test_review_policy_conservative_approves_high_confidence_low_risk_candidates() -> None:
    approved = ReviewPolicy("conservative").decide(
        _candidate("cand_1", confidence=0.86, importance=0.7)
    )
    pending = ReviewPolicy("conservative").decide(
        _candidate("cand_2", confidence=0.64, importance=0.7)
    )

    assert approved.status == "approved"
    assert "conservative_auto_approved" in approved.reasons
    assert pending.status == "pending_review"
    assert "below_auto_approve_threshold" in pending.reasons


def test_review_policy_safe_auto_keeps_user_preferences_pending() -> None:
    decision = ReviewPolicy("safe-auto").decide(
        _candidate("cand_1", kind="user_preference", title="User prefers quiet mornings")
    )

    assert decision.status == "pending_review"
    assert "sensitive_kind_requires_review" in decision.reasons


def test_write_review_artifacts_splits_candidates_and_rejections(tmp_path) -> None:
    approved_candidate = _candidate("cand_approved", confidence=0.9, importance=0.8)
    pending_candidate = _candidate("cand_pending", confidence=0.5, importance=0.8)
    rejection = Rejection(
        item_id="cand_rejected",
        item_type="candidate_record",
        reasons=["duplicate_candidate"],
        metadata={"merged_into": "cand_approved"},
    )

    result = write_review_artifacts(
        tmp_path,
        candidates=[approved_candidate, pending_candidate],
        rejections=[rejection],
        policy=ReviewPolicy("conservative"),
    )

    assert isinstance(result, ReviewResult)
    assert [candidate.candidate_id for candidate in result.approved] == ["cand_approved"]
    assert [candidate.candidate_id for candidate in result.pending] == ["cand_pending"]
    assert result.rejected == [rejection]
    assert read_jsonl(tmp_path / "candidate-records.jsonl")
    assert read_jsonl(tmp_path / "merged-records.jsonl")
    assert read_jsonl(tmp_path / "approved-records.jsonl")[0]["candidate_id"] == "cand_approved"
    assert read_jsonl(tmp_path / "pending-records.jsonl")[0]["candidate_id"] == "cand_pending"
    assert read_jsonl(tmp_path / "rejected-candidates.jsonl")[0]["item_id"] == "cand_rejected"
    review_markdown = (tmp_path / "review.md").read_text(encoding="utf-8")
    assert "# Ingestion Candidate Review" in review_markdown
    assert "Approved: 1" in review_markdown
    assert "Pending review: 1" in review_markdown
    assert "Rejected: 1" in review_markdown
    assert "Project capsule: demo" in review_markdown
