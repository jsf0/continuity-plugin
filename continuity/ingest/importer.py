"""Import approved ingestion candidates into the continuity store."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from continuity.context_labels import context_from_mapping, context_to_mapping
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

    def import_records(
        self,
        candidates: list[CandidateRecord],
        *,
        dry_run: bool,
        documents: list[object] | None = None,
        segments: list[object] | None = None,
    ) -> ImportResult:
        created: list[str] = []
        updated: list[str] = []
        skipped: list[str] = []
        failed: list[tuple[str, str]] = []
        segment_index = _segment_index(segments or [])

        if not dry_run and (documents or segments):
            self.store.upsert_corpus_sources(documents or [], segments or [])

        for candidate in candidates:
            try:
                record = candidate_to_context_record(candidate, segment_index=segment_index)
                existing = self.store.get_record(record.id)
                if dry_run:
                    skipped.append(candidate.candidate_id)
                    continue
                self.store.upsert_record(record)
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


def candidate_to_context_record(
    candidate: CandidateRecord, *, segment_index: dict[str, dict[str, object]] | None = None
) -> ContextRecord:
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
        sources=[
            _source_ref(source_ref, segment_index=segment_index or {})
            for source_ref in candidate.source_refs
        ],
        confidence=candidate.confidence,
        importance=candidate.importance,
        trust_level=candidate.trust_level,
    )
    record, _assessment = enrich_record_metadata(record)
    context_payload = context_to_mapping(context_from_mapping(candidate.ingestion))
    if context_payload["labels"]:
        record = ContextRecord.from_dict(
            {**record.to_dict(), "quality": {**record.quality, "context": context_payload}}
        )
    return ContextRecord.from_dict(
        {
            **record.to_dict(),
            "source_hash": stable_hash(
                {
                    "candidate_id": candidate.candidate_id,
                    "source_refs": [source_ref.to_dict() for source_ref in candidate.source_refs],
                    "summary": candidate.summary,
                    "context": context_payload if context_payload["labels"] else {},
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


def _source_ref(
    source_ref: IngestSourceRef, *, segment_index: dict[str, dict[str, object]]
) -> SourceRef:
    segment = segment_index.get(source_ref.segment_id or "")
    document_id = _optional_str(segment.get("source_id")) if segment else None
    text = str(segment.get("text") or "") if segment else ""
    content_hash = source_ref.content_hash or (_sha256_text(text) if text else None)
    return SourceRef(
        type="corpus_segment" if source_ref.segment_id and segment else source_ref.type,
        id=source_ref.segment_id,
        uri=source_ref.uri or source_ref.url or source_ref.path,
        range=_range_label(source_ref),
        label=source_ref.section or source_ref.title,
        created_at=None,
        document_id=document_id,
        segment_id=source_ref.segment_id,
        content_hash=content_hash,
        metadata={"source_type": source_ref.type, **source_ref.metadata},
    )


def _segment_index(segments: list[object]) -> dict[str, dict[str, object]]:
    indexed: dict[str, dict[str, object]] = {}
    for segment in segments:
        payload = segment.to_dict() if hasattr(segment, "to_dict") else segment  # type: ignore[attr-defined]
        if not isinstance(payload, dict):
            continue
        segment_id = _optional_str(payload.get("segment_id") or payload.get("id"))
        if segment_id:
            indexed[segment_id] = dict(payload)
    return indexed


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _range_label(source_ref: IngestSourceRef) -> str | None:
    if source_ref.line_start is not None and source_ref.line_end is not None:
        return f"lines {source_ref.line_start}-{source_ref.line_end}"
    if source_ref.page_start is not None and source_ref.page_end is not None:
        return f"pages {source_ref.page_start}-{source_ref.page_end}"
    return None
