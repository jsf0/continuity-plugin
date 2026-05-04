"""Stale-record discovery for continuity memory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher

from .models import ContextRecord


@dataclass(frozen=True)
class StaleCandidate:
    """A deterministic stale-record recommendation."""

    record_id: str
    reason: str
    superseded_by: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.record_id,
            "reason": self.reason,
            "superseded_by": self.superseded_by,
        }


def find_stale_candidates(
    records: list[ContextRecord], *, stale_after_days: int = 180, limit: int = 20
) -> list[StaleCandidate]:
    """Return conservative stale-record candidates without mutating storage."""
    candidates: dict[str, StaleCandidate] = {}
    active_records = [record for record in records if record.status == "active"]

    for record in active_records:
        if _is_expired(record):
            candidates[record.id] = StaleCandidate(record.id, "expires_at is in the past")

    _add_superseded_project_state_candidates(active_records, candidates)
    _add_mirrored_duplicate_candidates(active_records, candidates)
    _add_misclassified_extraction_dump_candidates(active_records, candidates)
    _add_age_candidates(active_records, candidates, stale_after_days=stale_after_days)

    ordered = sorted(
        candidates.values(),
        key=lambda candidate: _record_sort_key(
            records_by_id=records, record_id=candidate.record_id
        ),
    )
    return ordered[:limit]


def _add_superseded_project_state_candidates(
    records: list[ContextRecord], candidates: dict[str, StaleCandidate]
) -> None:
    grouped: dict[tuple[str | None, str | None], list[ContextRecord]] = {}
    for record in records:
        if record.kind == "active_project_state":
            grouped.setdefault((record.scope_project, record.scope_repo), []).append(record)
    for group in grouped.values():
        if len(group) < 2:
            continue
        newest = max(group, key=_freshness_key)
        for record in group:
            if record.id == newest.id:
                continue
            candidates[record.id] = StaleCandidate(
                record.id,
                "superseded by newer active_project_state for the same scope",
                superseded_by=newest.id,
            )


def _add_mirrored_duplicate_candidates(
    records: list[ContextRecord], candidates: dict[str, StaleCandidate]
) -> None:
    grouped: dict[tuple[str, str, str | None, str | None, str | None], list[ContextRecord]] = {}
    for record in records:
        if record.trust_level != "built_in_memory_mirror":
            continue
        grouped.setdefault(
            (
                record.kind,
                record.title,
                record.scope_project,
                record.scope_repo,
                _source_bucket(record),
            ),
            [],
        ).append(record)
    for group in grouped.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=_freshness_key, reverse=True)
        for index, newer in enumerate(ordered):
            for older in ordered[index + 1 :]:
                if older.id in candidates:
                    continue
                if _records_appear_superseded(older, newer):
                    candidates[older.id] = StaleCandidate(
                        older.id,
                        "older built-in memory mirror appears superseded by a newer similar mirror",
                        superseded_by=newer.id,
                    )

    _add_project_status_supersession_candidates(records, candidates)


def _add_project_status_supersession_candidates(
    records: list[ContextRecord], candidates: dict[str, StaleCandidate]
) -> None:
    """Archive older project-status mirrors superseded by newer status mirrors.

    Status memories are often replace-style snapshots where exact wording can
    change substantially after a fix.  Similarity alone misses those updates, so
    group by project entity plus source bucket and compare chronological pairs.
    """
    grouped: dict[tuple[str, str | None], list[ContextRecord]] = {}
    for record in records:
        if record.trust_level != "built_in_memory_mirror":
            continue
        project_key = _project_status_key(record)
        if project_key is None:
            continue
        grouped.setdefault((project_key, _source_bucket(record)), []).append(record)

    for group in grouped.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=_freshness_key, reverse=True)
        newest = ordered[0]
        for older in ordered[1:]:
            if older.id in candidates:
                continue
            candidates[older.id] = StaleCandidate(
                older.id,
                "older project status mirror superseded by newer status for the same project/entity",
                superseded_by=newest.id,
            )


def _add_misclassified_extraction_dump_candidates(
    records: list[ContextRecord], candidates: dict[str, StaleCandidate]
) -> None:
    """Flag accidental session extractions of skills/docs as memories."""
    procedural_markers = {
        "rag / vector db guidance",
        "context_record_association_edges",
        "embedding_text",
        "reranker",
        "continuity_debug_retrieval",
        "skill_dir",
        "required_environment_variables",
    }
    for record in records:
        if record.id in candidates:
            continue
        if record.trust_level != "session_extracted" or record.kind != "user_preference":
            continue
        text = " ".join([record.title, record.summary, record.details or ""]).lower()
        marker_hits = sum(1 for marker in procedural_markers if marker in text)
        if marker_hits >= 2 or len(record.entities) >= 40:
            candidates[record.id] = StaleCandidate(
                record.id,
                "misclassified extracted procedural/skill dump, not a durable user preference",
            )


def _add_age_candidates(
    records: list[ContextRecord],
    candidates: dict[str, StaleCandidate],
    *,
    stale_after_days: int,
) -> None:
    if stale_after_days <= 0:
        return
    cutoff = datetime.now(UTC).timestamp() - stale_after_days * 24 * 60 * 60
    for record in records:
        if record.id in candidates:
            continue
        if record.trust_level == "explicit_user" or record.kind == "user_preference":
            continue
        if record.importance > 0.4:
            continue
        last_confirmed = (
            _parse_timestamp(record.last_confirmed_at) if record.last_confirmed_at else None
        )
        if last_confirmed is not None and last_confirmed.timestamp() >= cutoff:
            continue
        last_accessed = (
            _parse_timestamp(record.last_accessed_at) if record.last_accessed_at else None
        )
        if last_accessed is not None and last_accessed.timestamp() >= cutoff:
            continue
        updated_at = _parse_timestamp(record.updated_at)
        if updated_at is not None and updated_at.timestamp() < cutoff:
            candidates[record.id] = StaleCandidate(
                record.id,
                f"low-importance record older than stale_after_days={stale_after_days}",
            )


def _is_expired(record: ContextRecord) -> bool:
    if not record.expires_at:
        return False
    expires_at = _parse_timestamp(record.expires_at)
    return expires_at is not None and expires_at <= datetime.now(UTC)


def _freshness_key(record: ContextRecord) -> tuple[datetime, str]:
    return (
        _parse_timestamp(record.updated_at) or datetime.min.replace(tzinfo=UTC),
        record.id,
    )


def _record_sort_key(records_by_id: list[ContextRecord], record_id: str) -> tuple[datetime, str]:
    record = next((item for item in records_by_id if item.id == record_id), None)
    if record is None:
        return (datetime.max.replace(tzinfo=UTC), record_id)
    return (
        _parse_timestamp(record.updated_at) or datetime.max.replace(tzinfo=UTC),
        record.id,
    )


def _source_bucket(record: ContextRecord) -> str | None:
    for source in record.sources:
        if source.type == "built_in_memory":
            return source.id
    return None


def _similar(left: str, right: str) -> float:
    return SequenceMatcher(a=left.lower(), b=right.lower()).ratio()


def _records_appear_superseded(older: ContextRecord, newer: ContextRecord) -> bool:
    return (
        _similar(older.summary, newer.summary) >= 0.68
        or _shared_terms(older.summary, newer.summary) >= 4
    )


def _project_status_key(record: ContextRecord) -> str | None:
    terms = _terms(" ".join([record.summary, record.title, *record.tags, *record.entities]))
    if "status" not in terms:
        return None
    for entity in sorted(record.entities):
        entity_terms = _terms(entity)
        if entity_terms:
            return " ".join(sorted(entity_terms))
    known_project_terms = {"guard-proxy", "hermes-agent", "continuity", "llama.cpp"}
    matches = sorted(terms & known_project_terms)
    return matches[0] if matches else None


def _shared_terms(left: str, right: str) -> int:
    return len(_terms(left) & _terms(right))


def _terms(text: str) -> set[str]:
    import re

    return {term for term in re.findall(r"[\w:-]+", text.lower()) if len(term) >= 4}


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
