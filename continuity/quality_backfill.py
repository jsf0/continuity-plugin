"""Retrospective quality recomputation and backfill helpers."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .models import utc_now
from .record_quality import enrich_record_metadata
from .store import ContinuityStore


@dataclass(frozen=True)
class QualityBackfillReport:
    """Summary of recomputed quality metadata for existing records."""

    record_count: int
    warning_count: int
    review_required_count: int
    drift_count: int
    updated_count: int = 0
    top_warnings: list[tuple[str, int]] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_count": self.record_count,
            "warning_count": self.warning_count,
            "review_required_count": self.review_required_count,
            "drift_count": self.drift_count,
            "updated_count": self.updated_count,
            "top_warnings": self.top_warnings,
            "records": self.records,
        }


def build_quality_backfill_report(
    store: ContinuityStore,
    *,
    limit: int = 100,
    active_only: bool = False,
) -> QualityBackfillReport:
    """Recompute quality for records and report warning/drift inventory.

    This is a dry-run helper: it never mutates stored records.  Drift means the
    recomputed quality JSON differs from the persisted quality JSON, including
    pre-migration records with empty quality metadata.
    """

    records = store.list_records()
    if active_only:
        records = [record for record in records if record.status == "active"]

    report_records: list[dict[str, Any]] = []
    warnings: Counter[str] = Counter()
    review_required_count = 0
    drift_count = 0
    for record in records:
        _enriched, assessment = enrich_record_metadata(record)
        recomputed_quality = _normalized_quality(assessment.to_dict())
        persisted_quality = _normalized_quality(record.quality or {})
        recomputed_warnings = _quality_warnings(recomputed_quality)
        persisted_warnings = _quality_warnings(persisted_quality)
        recomputed_review_required = bool(recomputed_quality.get("review_required"))
        persisted_review_required = bool(persisted_quality.get("review_required"))
        quality_differs = recomputed_quality != persisted_quality
        if quality_differs:
            drift_count += 1
        if recomputed_warnings:
            warnings.update(recomputed_warnings)
        if recomputed_review_required:
            review_required_count += 1
        if recomputed_warnings or recomputed_review_required or quality_differs:
            reasons: list[str] = []
            if recomputed_warnings:
                reasons.append("recomputed_warnings")
            if recomputed_review_required:
                reasons.append("review_required")
            if quality_differs:
                reasons.append("quality_differs")
            report_records.append(
                {
                    "id": record.id,
                    "kind": record.kind,
                    "title": record.title,
                    "status": record.status,
                    "trust_level": record.trust_level,
                    "scope_project": record.scope_project,
                    "persisted_warnings": persisted_warnings,
                    "recomputed_warnings": recomputed_warnings,
                    "persisted_review_required": persisted_review_required,
                    "recomputed_review_required": recomputed_review_required,
                    "persisted_score": persisted_quality.get("score"),
                    "recomputed_score": recomputed_quality.get("score"),
                    "reasons": reasons,
                }
            )

    report_records.sort(
        key=lambda item: (
            0 if "review_required" in item["reasons"] else 1,
            float(item.get("recomputed_score") or 1.0),
            str(item["id"]),
        )
    )
    return QualityBackfillReport(
        record_count=len(records),
        warning_count=sum(1 for item in report_records if item["recomputed_warnings"]),
        review_required_count=review_required_count,
        drift_count=drift_count,
        updated_count=0,
        top_warnings=warnings.most_common(),
        records=report_records[: max(1, limit)],
    )


def apply_quality_backfill(
    store: ContinuityStore,
    *,
    limit: int | None = None,
    active_only: bool = False,
) -> QualityBackfillReport:
    """Persist recomputed quality JSON for records whose quality differs.

    Only ``quality_json`` and ``updated_at`` are updated.  Tags, entities,
    details, embedding text, FTS rows, vectors, and association edges are left
    untouched so diagnostics do not become retrieval content.
    """

    records = store.list_records()
    if active_only:
        records = [record for record in records if record.status == "active"]

    changed: list[tuple[str, dict[str, Any]]] = []
    for record in records:
        _enriched, assessment = enrich_record_metadata(record)
        recomputed_quality = _normalized_quality(assessment.to_dict())
        persisted_quality = _normalized_quality(record.quality or {})
        if recomputed_quality != persisted_quality:
            changed.append((record.id, recomputed_quality))
        if limit is not None and len(changed) >= limit:
            break

    now = utc_now()
    with store.connect() as conn:
        for record_id, quality in changed:
            conn.execute(
                "UPDATE context_records SET quality_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(quality, sort_keys=True), now, record_id),
            )

    report = build_quality_backfill_report(store, limit=limit or 100, active_only=active_only)
    return QualityBackfillReport(
        record_count=report.record_count,
        warning_count=report.warning_count,
        review_required_count=report.review_required_count,
        drift_count=report.drift_count,
        updated_count=len(changed),
        top_warnings=report.top_warnings,
        records=report.records,
    )


def _quality_warnings(quality: dict[str, Any]) -> list[str]:
    warnings = quality.get("warnings", [])
    if not isinstance(warnings, list):
        return []
    return [str(warning) for warning in warnings]


def _normalized_quality(quality: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(quality, sort_keys=True))
