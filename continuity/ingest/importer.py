"""Import approved ingestion candidates into the continuity store."""

from __future__ import annotations

from dataclasses import dataclass

from continuity.ingest.models import (
    CandidateRecord,
    stable_hash,
    stable_id,
)
from continuity.ingest.models import (
    SourceRef as IngestSourceRef,
)
from continuity.models import ContextRecord, SourceRef
from continuity.record_quality import enrich_record_metadata
from continuity.store import ContinuityStore


@dataclass(frozen=True)
class ImportResult:
    """Result of importing candidate records."""

    dry_run: bool
    created: list[str]
    updated: list[str]
    skipped: list[str]
    failed: list[tuple[str, str]]


class ContinuityImporter:
    """Write approved ingestion candidates to an existing ContinuityStore."""

    def __init__(self, store: ContinuityStore) -> None:
        self.store = store
        self.store.migrate()

    def import_records(self, candidates: list[CandidateRecord], *, dry_run: bool) -> ImportResult:
        created: list[str] = []
        updated: list[str] = []
        skipped: list[str] = []
        failed: list[tuple[str, str]] = []

        for candidate in candidates:
            try:
                record = candidate_to_context_record(candidate)
                existing = self.store.get_record(record.id)
                if dry_run:
                    skipped.append(candidate.candidate_id)
                    continue
                self.store.upsert_record(record, create_associations=False)
                if existing:
                    updated.append(record.id)
                else:
                    created.append(record.id)
            except (TypeError, ValueError) as exc:
                failed.append((candidate.candidate_id, str(exc)))
        return ImportResult(
            dry_run=dry_run,
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
        )


def candidate_to_context_record(candidate: CandidateRecord) -> ContextRecord:
    """Convert a candidate record into a continuity ContextRecord."""

    record = ContextRecord.new(
        id=imported_record_id(candidate),
        kind=candidate.kind,
        title=candidate.title,
        summary=candidate.summary,
        scope_user=candidate.scope_user,
        scope_project=candidate.scope_project,
        scope_repo=candidate.scope_repo,
        scope_profile=candidate.scope_profile,
        details=candidate.details,
        tags=candidate.tags,
        entities=candidate.entities,
        sources=[_source_ref(source_ref) for source_ref in candidate.source_refs],
        confidence=candidate.confidence,
        importance=candidate.importance,
        trust_level=candidate.trust_level,
    )
    record, _assessment = enrich_record_metadata(record)
    return ContextRecord.from_dict(
        {
            **record.to_dict(),
            "source_hash": stable_hash(
                {
                    "candidate_id": candidate.candidate_id,
                    "source_refs": [source_ref.to_dict() for source_ref in candidate.source_refs],
                    "summary": candidate.summary,
                }
            ),
        }
    )


def imported_record_id(candidate: CandidateRecord) -> str:
    """Return deterministic continuity record ID for an imported candidate."""

    source_ids = [
        source_ref.segment_id or source_ref.uri or source_ref.path
        for source_ref in candidate.source_refs
    ]
    return stable_id(
        candidate.candidate_id,
        candidate.kind,
        candidate.scope_project or "",
        candidate.scope_repo or "",
        candidate.title,
        source_ids,
    )


def _source_ref(source_ref: IngestSourceRef) -> SourceRef:
    return SourceRef(
        type=source_ref.type,
        id=source_ref.segment_id,
        uri=source_ref.uri or source_ref.url or source_ref.path,
        range=_range_label(source_ref),
        label=source_ref.section or source_ref.title,
        created_at=None,
    )


def _range_label(source_ref: IngestSourceRef) -> str | None:
    if source_ref.line_start is not None and source_ref.line_end is not None:
        return f"lines {source_ref.line_start}-{source_ref.line_end}"
    if source_ref.page_start is not None and source_ref.page_end is not None:
        return f"pages {source_ref.page_start}-{source_ref.page_end}"
    return None
