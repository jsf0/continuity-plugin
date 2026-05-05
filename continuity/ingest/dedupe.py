"""Deduplication helpers for ingestion candidate records."""

from __future__ import annotations

from dataclasses import dataclass, replace

from continuity.ingest.models import CandidateRecord, Rejection, SourceRef


@dataclass(frozen=True)
class DedupeResult:
    """Result of candidate deduplication."""

    accepted: list[CandidateRecord]
    duplicates: list[tuple[str, str]]
    rejections: list[Rejection]


class BasicDeduper:
    """Merge obvious duplicate candidates using deterministic keys."""

    def dedupe(self, candidates: list[CandidateRecord]) -> DedupeResult:
        accepted: list[CandidateRecord] = []
        duplicates: list[tuple[str, str]] = []
        rejections: list[Rejection] = []
        title_keys: dict[tuple[str, str, str, str | None], int] = {}
        source_keys: dict[tuple[str, str | None, str | None, str | None], int] = {}

        for candidate in candidates:
            existing_index = self._find_existing_index(candidate, title_keys, source_keys)
            if existing_index is None:
                accepted.append(candidate)
                self._index_candidate(candidate, len(accepted) - 1, title_keys, source_keys)
                continue

            existing = accepted[existing_index]
            merged = _merge_candidates(existing, candidate)
            accepted[existing_index] = merged
            self._index_candidate(merged, existing_index, title_keys, source_keys)
            duplicates.append((candidate.candidate_id, existing.candidate_id))
            rejections.append(
                Rejection(
                    item_id=candidate.candidate_id,
                    item_type="candidate_record",
                    reasons=["duplicate_candidate"],
                    metadata={"merged_into": existing.candidate_id},
                )
            )

        return DedupeResult(accepted=accepted, duplicates=duplicates, rejections=rejections)

    def _find_existing_index(
        self,
        candidate: CandidateRecord,
        title_keys: dict[tuple[str, str, str, str | None], int],
        source_keys: dict[tuple[str, str | None, str | None, str | None], int],
    ) -> int | None:
        title_key = _title_key(candidate)
        if title_key in title_keys:
            return title_keys[title_key]
        for source_key in _source_keys(candidate):
            if source_key in source_keys:
                return source_keys[source_key]
        return None

    def _index_candidate(
        self,
        candidate: CandidateRecord,
        index: int,
        title_keys: dict[tuple[str, str, str, str | None], int],
        source_keys: dict[tuple[str, str | None, str | None, str | None], int],
    ) -> None:
        title_keys[_title_key(candidate)] = index
        for source_key in _source_keys(candidate):
            source_keys[source_key] = index


def _title_key(candidate: CandidateRecord) -> tuple[str, str, str, str | None]:
    return (
        candidate.kind,
        " ".join(candidate.title.casefold().split()),
        candidate.scope_project or "",
        candidate.scope_repo,
    )


def _source_keys(
    candidate: CandidateRecord,
) -> list[tuple[str, str | None, str | None, str | None]]:
    return [
        (candidate.kind, source_ref.uri, source_ref.segment_id, candidate.scope_project)
        for source_ref in candidate.source_refs
        if source_ref.uri or source_ref.segment_id
    ]


def _merge_candidates(first: CandidateRecord, second: CandidateRecord) -> CandidateRecord:
    return replace(
        first,
        tags=_merge_strings(first.tags, second.tags),
        entities=_merge_strings(first.entities, second.entities),
        source_refs=_merge_source_refs(first.source_refs, second.source_refs),
        confidence=max(first.confidence, second.confidence),
        importance=max(first.importance, second.importance),
        ingestion={**first.ingestion, "merged_candidate_ids": _merged_ids(first, second)},
    )


def _merge_strings(first: list[str], second: list[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for value in [*first, *second]:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            values.append(value)
    return values


def _merge_source_refs(first: list[SourceRef], second: list[SourceRef]) -> list[SourceRef]:
    refs: list[SourceRef] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for ref in [*first, *second]:
        key = (ref.type, ref.uri, ref.segment_id)
        if key not in seen:
            seen.add(key)
            refs.append(ref)
    return refs


def _merged_ids(first: CandidateRecord, second: CandidateRecord) -> list[str]:
    existing = first.ingestion.get("merged_candidate_ids")
    values = list(existing) if isinstance(existing, list) else [first.candidate_id]
    if second.candidate_id not in values:
        values.append(second.candidate_id)
    return values
