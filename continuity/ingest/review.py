"""Review policies and review artifact generation for ingestion candidates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from continuity.ingest.jsonl import write_jsonl
from continuity.ingest.models import CandidateRecord, Rejection, ReviewDecision

_SENSITIVE_KINDS = {"user_preference", "personal_fact", "policy_rule", "legal_obligation"}


@dataclass(frozen=True)
class ReviewResult:
    """Candidate review split produced by a review policy."""

    approved: list[CandidateRecord]
    pending: list[CandidateRecord]
    rejected: list[Rejection]
    decisions: list[ReviewDecision]


class ReviewPolicy:
    """Deterministic review policy for candidate records."""

    def __init__(self, mode: str) -> None:
        if mode not in {"propose", "require-review", "conservative", "safe-auto"}:
            raise ValueError("unknown review policy mode")
        self.mode = mode

    def decide(self, candidate: CandidateRecord) -> ReviewDecision:
        if self.mode == "propose":
            return ReviewDecision(
                candidate_id=candidate.candidate_id,
                status="pending_review",
                reasons=["propose_mode"],
            )
        if self.mode == "require-review":
            return ReviewDecision(
                candidate_id=candidate.candidate_id,
                status="pending_review",
                reasons=["review_required"],
            )
        if candidate.kind in _SENSITIVE_KINDS:
            return ReviewDecision(
                candidate_id=candidate.candidate_id,
                status="pending_review",
                reasons=["sensitive_kind_requires_review"],
            )
        if self.mode == "safe-auto":
            if candidate.confidence >= 0.75 and candidate.importance >= 0.5:
                return ReviewDecision(
                    candidate_id=candidate.candidate_id,
                    status="approved",
                    reasons=["safe_auto_approved"],
                )
            return ReviewDecision(
                candidate_id=candidate.candidate_id,
                status="pending_review",
                reasons=["below_auto_approve_threshold"],
            )
        if candidate.confidence >= 0.8 and candidate.importance >= 0.6:
            return ReviewDecision(
                candidate_id=candidate.candidate_id,
                status="approved",
                reasons=["conservative_auto_approved"],
            )
        return ReviewDecision(
            candidate_id=candidate.candidate_id,
            status="pending_review",
            reasons=["below_auto_approve_threshold"],
        )


def write_review_artifacts(
    output_dir: str | Path,
    *,
    candidates: list[CandidateRecord],
    rejections: list[Rejection],
    policy: ReviewPolicy,
    raw_candidates: list[CandidateRecord] | None = None,
) -> ReviewResult:
    """Split candidates by review policy and write JSONL/Markdown artifacts."""

    approved: list[CandidateRecord] = []
    pending: list[CandidateRecord] = []
    decisions: list[ReviewDecision] = []
    for candidate in candidates:
        decision = policy.decide(candidate)
        decisions.append(decision)
        if decision.status == "approved":
            approved.append(candidate)
        else:
            pending.append(candidate)

    result = ReviewResult(
        approved=approved,
        pending=pending,
        rejected=rejections,
        decisions=decisions,
    )
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    write_jsonl(
        output_path / "candidate-records.jsonl",
        [candidate.to_dict() for candidate in raw_candidates or candidates],
    )
    write_jsonl(
        output_path / "merged-records.jsonl", [candidate.to_dict() for candidate in candidates]
    )
    write_jsonl(
        output_path / "approved-records.jsonl", [candidate.to_dict() for candidate in approved]
    )
    write_jsonl(
        output_path / "pending-records.jsonl", [candidate.to_dict() for candidate in pending]
    )
    write_jsonl(
        output_path / "rejected-candidates.jsonl", [rejection.to_dict() for rejection in rejections]
    )
    write_jsonl(
        output_path / "review-decisions.jsonl", [decision.to_dict() for decision in decisions]
    )
    (output_path / "review.md").write_text(_render_review_markdown(result), encoding="utf-8")
    return result


def _render_review_markdown(result: ReviewResult) -> str:
    lines = [
        "# Ingestion Candidate Review",
        "",
        "## Summary",
        "",
        f"Approved: {len(result.approved)}",
        f"Pending review: {len(result.pending)}",
        f"Rejected: {len(result.rejected)}",
        "",
    ]
    if result.approved:
        lines.extend(["## Approved", ""])
        lines.extend(_candidate_lines(result.approved))
    if result.pending:
        lines.extend(["## Pending Review", ""])
        lines.extend(_candidate_lines(result.pending))
    if result.rejected:
        lines.extend(["## Rejected", ""])
        for rejection in result.rejected:
            lines.append(f"- `{rejection.item_id}`: {', '.join(rejection.reasons)}")
        lines.append("")
    return "\n".join(lines)


def _candidate_lines(candidates: list[CandidateRecord]) -> list[str]:
    lines: list[str] = []
    for candidate in candidates:
        lines.append(f"### {candidate.title}")
        lines.append("")
        lines.append(f"- ID: `{candidate.candidate_id}`")
        lines.append(f"- Kind: `{candidate.kind}`")
        lines.append(f"- Confidence: {candidate.confidence:.2f}")
        lines.append(f"- Importance: {candidate.importance:.2f}")
        if candidate.tags:
            lines.append(f"- Tags: {', '.join(candidate.tags)}")
        lines.append("")
        lines.append(candidate.summary)
        lines.append("")
    return lines
