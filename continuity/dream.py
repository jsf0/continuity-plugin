"""Scheduled offline maintenance ("dreaming") for continuity memory."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import DreamConfig
from .staleness import find_stale_candidates
from .store import ContinuityStore

REPORT_MODE = "report"
ARCHIVE_SAFE_MODE = "archive-safe"
ARCHIVE_ALL_MODE = "archive-all-candidates"
VALID_DREAM_MODES = frozenset({REPORT_MODE, ARCHIVE_SAFE_MODE, ARCHIVE_ALL_MODE})


def should_run_scheduled_dream(
    now: datetime,
    schedule: str,
    last_run_at: str | None,
    *,
    timezone_name: str = "UTC",
) -> bool:
    """Return true once per local date after the configured HH:MM schedule."""
    zone = _zone(timezone_name)
    local_now = now.astimezone(zone)
    hour, minute = _parse_schedule(schedule)
    scheduled_today = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if local_now < scheduled_today:
        return False
    last_run = _parse_timestamp(last_run_at)
    if last_run is None:
        return True
    return last_run.astimezone(zone).date() < local_now.date()


def run_dream_cycle(
    store: ContinuityStore,
    config: DreamConfig,
    *,
    mode: str | None = None,
    stale_after_days: int = 180,
    limit: int | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Run one dream maintenance cycle and persist a compact report.

    Report mode only inspects. Archive modes soft-archive stale candidates; hard
    deletion is deliberately outside the dream cycle.
    """
    effective_mode = _normalize_mode(mode or config.mode)
    effective_limit = max(1, limit or config.max_archives_per_run)
    timestamp = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    started_at = timestamp.isoformat().replace("+00:00", "Z")
    before_counts = _status_counts(store)
    candidates = find_stale_candidates(
        store.list_records(), stale_after_days=stale_after_days, limit=effective_limit
    )
    archived_ids: list[str] = []
    if effective_mode in {ARCHIVE_SAFE_MODE, ARCHIVE_ALL_MODE}:
        for candidate in candidates:
            if store.archive_record(
                candidate.record_id,
                reason=f"dream: {candidate.reason}",
                superseded_by=candidate.superseded_by,
            ):
                archived_ids.append(candidate.record_id)
    after_counts = _status_counts(store)
    report: dict[str, object] = {
        "success": True,
        "mode": effective_mode,
        "started_at": started_at,
        "mutated": bool(archived_ids),
        "record_counts_before": before_counts,
        "record_counts_after": after_counts,
        "stale_candidates": [candidate.to_dict() for candidate in candidates],
        "archived_ids": archived_ids,
        "deleted_ids": [],
        "notes": _notes(effective_mode, candidates, archived_ids),
    }
    store.set_state("dream:last_report", json.dumps(report, ensure_ascii=False, sort_keys=True))
    if effective_mode != REPORT_MODE:
        store.set_state("dream:last_run_at", started_at)
    return report


def _normalize_mode(value: str) -> str:
    mode = value.strip().lower()
    return mode if mode in VALID_DREAM_MODES else REPORT_MODE


def _status_counts(store: ContinuityStore) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in store.list_records():
        counts[record.status] = counts.get(record.status, 0) + 1
    return counts


def _notes(mode: str, candidates: object, archived_ids: list[str]) -> list[str]:
    candidate_count = len(candidates) if hasattr(candidates, "__len__") else 0
    if mode == REPORT_MODE:
        return [f"report-only dream; {candidate_count} stale candidate(s), no mutations"]
    return [
        f"archived {len(archived_ids)} of {candidate_count} stale candidate(s); no hard deletes"
    ]


def _parse_schedule(schedule: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = schedule.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError:
        return (3, 30)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return (3, 30)
    return (hour, minute)


def _zone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


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
