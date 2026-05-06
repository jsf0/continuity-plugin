"""Markdown reports for ingestion runs."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from statistics import mean

from continuity.context_labels import context_from_mapping
from continuity.ingest.models import (
    CandidateRecord,
    IngestionRunManifest,
    Rejection,
    SourceDocument,
    SourceSegment,
)
from continuity.ingest.review import ReviewResult


def render_dry_run_report(manifest: IngestionRunManifest) -> str:
    """Render a compact human-readable dry-run report."""

    return "\n".join(
        [
            "# Ingestion Dry Run Report",
            "",
            f"Run ID: {manifest.run_id}",
            f"Recipe: {manifest.recipe}",
            f"Created at: {manifest.created_at}",
            "",
            "## Summary",
            "",
            f"Sources discovered: {manifest.source_count}",
            f"Segments generated: {manifest.segment_count}",
            f"Candidate records: {manifest.candidate_count}",
            f"Approved records: {manifest.approved_count}",
            f"Imported records: {manifest.imported_count}",
            f"Rejected items: {manifest.rejected_count}",
            "",
            "Candidate extraction, validation, dedupe, review splitting, and eval generation were performed.",
            "No records were imported; apply approved records explicitly with the import command.",
            "Machine-readable run statistics were written to `ingestion-stats.json` for scale/debug review.",
            "",
        ]
    )


def build_ingestion_stats(
    *,
    manifest: IngestionRunManifest,
    documents: Sequence[SourceDocument],
    segments: Sequence[SourceSegment],
    candidates: Sequence[CandidateRecord],
    merged_candidates: Sequence[CandidateRecord],
    rejections: Sequence[Rejection],
    review_result: ReviewResult | None,
) -> dict[str, object]:
    """Build machine-readable run statistics for large-corpus inspection."""

    segment_lengths = [len(segment.text) for segment in segments]
    document_types = {document.source_id: document.source_type for document in documents}
    approved_count = len(review_result.approved) if review_result else 0
    pending_count = len(review_result.pending) if review_result else 0
    rejected_review_count = len(review_result.rejected) if review_result else 0
    return {
        "summary": {
            "run_id": manifest.run_id,
            "recipe": manifest.recipe,
            "source_count": manifest.source_count,
            "segment_count": manifest.segment_count,
            "candidate_count": manifest.candidate_count,
            "merged_candidate_count": len(merged_candidates),
            "approved_count": approved_count,
            "pending_count": pending_count,
            "review_rejected_count": rejected_review_count,
            "rejected_count": manifest.rejected_count,
        },
        "sources": {
            "by_type": _count(
                getattr(document, "source_type", "unknown") for document in documents
            ),
            "by_collection": _count(document.collection or "none" for document in documents),
        },
        "segments": {
            "count": len(segment_lengths),
            "total_chars": sum(segment_lengths),
            "min_chars": min(segment_lengths) if segment_lengths else 0,
            "max_chars": max(segment_lengths) if segment_lengths else 0,
            "avg_chars": round(mean(segment_lengths), 2) if segment_lengths else 0.0,
            "by_source_type": _count(
                document_types.get(segment.source_id, "unknown") for segment in segments
            ),
        },
        "candidates": {
            "by_kind": _count(candidate.kind for candidate in candidates),
            "by_trust_level": _count(candidate.trust_level for candidate in candidates),
            "by_scope_project": _count(
                candidate.scope_project or "none" for candidate in candidates
            ),
            "avg_confidence": _avg(candidate.confidence for candidate in candidates),
            "avg_importance": _avg(candidate.importance for candidate in candidates),
        },
        "context": _context_stats(documents, segments, candidates),
        "review": {
            "approved_count": approved_count,
            "pending_count": pending_count,
            "rejected_count": rejected_review_count,
        },
        "rejections": {
            "count": len(rejections),
            "by_reason": _count(reason for rejection in rejections for reason in rejection.reasons),
            "by_item_type": _count(rejection.item_type for rejection in rejections),
        },
    }


def _context_stats(
    documents: Sequence[SourceDocument],
    segments: Sequence[SourceSegment],
    candidates: Sequence[CandidateRecord],
) -> dict[str, object]:
    document_contexts = [context_from_mapping(document.metadata) for document in documents]
    segment_contexts = [context_from_mapping(segment.metadata) for segment in segments]
    candidate_contexts = [context_from_mapping(candidate.ingestion) for candidate in candidates]
    return {
        "documents_with_labels": sum(1 for context in document_contexts if context.labels),
        "segments_with_labels": sum(1 for context in segment_contexts if context.labels),
        "candidates_with_labels": sum(1 for context in candidate_contexts if context.labels),
        "by_collision_risk": _count(
            context.collision_risk for context in candidate_contexts if context.labels
        ),
        "by_partition_key": _count(
            key for context in candidate_contexts for key in context.partition_keys
        ),
        "by_label_key": _count(key for context in candidate_contexts for key in context.labels),
        "high_collision_without_partition": sum(
            1
            for context in candidate_contexts
            if context.labels and context.collision_risk == "high" and not context.partition_keys
        ),
    }


def _count(values: Iterable[object]) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def _avg(values: object) -> float:
    numbers = list(values)
    return round(mean(numbers), 3) if numbers else 0.0
