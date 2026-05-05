from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from continuity import ContinuityProvider
from continuity.config import ContinuityConfig
from continuity.dream import should_run_scheduled_dream
from continuity.models import ContextRecord


def make_project_state(
    record_id: str,
    *,
    summary: str,
    updated_at: str,
    scope_project: str = "hermes-continuity-memory",
) -> ContextRecord:
    return ContextRecord.from_dict(
        {
            "id": record_id,
            "kind": "active_project_state",
            "scope_project": scope_project,
            "title": "continuity status",
            "summary": summary,
            "tags": ["continuity", "status"],
            "entities": ["continuity"],
            "confidence": 0.9,
            "importance": 0.8,
            "trust_level": "agent_observed",
            "created_at": updated_at,
            "updated_at": updated_at,
            "status": "active",
        }
    )


def initialized_provider(
    tmp_path: Path, *, dream: dict[str, object] | None = None
) -> ContinuityProvider:
    provider = ContinuityProvider()
    provider.initialize(
        session_id="dream-phase10",
        hermes_home=str(tmp_path),
        continuity_config={"dream": dream or {}},
    )
    return provider


def call(
    provider: ContinuityProvider, tool_name: str, args: dict[str, object]
) -> dict[str, object]:
    return json.loads(provider.handle_tool_call(tool_name, args))


def test_config_parses_dream_cycle_settings() -> None:
    config = ContinuityConfig.from_mapping(
        {
            "dream": {
                "enabled": True,
                "schedule": "03:30",
                "timezone": "America/New_York",
                "mode": "archive-safe",
                "max_archives_per_run": 7,
                "run_on_initialize": False,
                "run_on_turn": True,
            }
        }
    )

    assert config.dream.enabled is True
    assert config.dream.schedule == "03:30"
    assert config.dream.timezone == "America/New_York"
    assert config.dream.mode == "archive-safe"
    assert config.dream.max_archives_per_run == 7
    assert config.dream.run_on_initialize is False
    assert config.dream.run_on_turn is True


def test_scheduled_dream_is_due_once_per_day_after_schedule() -> None:
    before_schedule = datetime(2026, 5, 5, 3, 29, tzinfo=UTC)
    after_schedule = datetime(2026, 5, 5, 3, 31, tzinfo=UTC)
    already_ran_today = "2026-05-05T03:35:00Z"
    ran_yesterday = "2026-05-04T03:35:00Z"

    assert should_run_scheduled_dream(before_schedule, "03:30", None, timezone_name="UTC") is False
    assert should_run_scheduled_dream(after_schedule, "03:30", None, timezone_name="UTC") is True
    assert (
        should_run_scheduled_dream(
            after_schedule,
            "03:30",
            already_ran_today,
            timezone_name="UTC",
        )
        is False
    )
    assert (
        should_run_scheduled_dream(
            after_schedule,
            "03:30",
            ran_yesterday,
            timezone_name="UTC",
        )
        is True
    )


def test_dream_tool_report_mode_reports_candidates_without_mutating(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path)
    assert provider._store is not None
    provider._store.upsert_record(
        make_project_state(
            "old_state",
            summary="continuity old noisy graph status",
            updated_at="2026-05-04T01:00:00Z",
        )
    )
    provider._store.upsert_record(
        make_project_state(
            "new_state",
            summary="continuity new facet-gated graph status",
            updated_at="2026-05-05T01:00:00Z",
        )
    )

    result = call(provider, "continuity_dream", {"mode": "report"})

    assert result["success"] is True
    assert result["mode"] == "report"
    assert result["mutated"] is False
    assert [candidate["id"] for candidate in result["stale_candidates"]] == ["old_state"]
    assert result["archived_ids"] == []
    assert provider._store.get_record("old_state").status == "active"  # type: ignore[union-attr]
    assert provider._store.get_state("dream:last_report") is not None


def test_dream_tool_archive_safe_archives_stale_candidates_and_records_last_run(
    tmp_path: Path,
) -> None:
    provider = initialized_provider(tmp_path)
    assert provider._store is not None
    provider._store.upsert_record(
        make_project_state(
            "old_state",
            summary="continuity old noisy graph status",
            updated_at="2026-05-04T01:00:00Z",
        )
    )
    provider._store.upsert_record(
        make_project_state(
            "new_state",
            summary="continuity new facet-gated graph status",
            updated_at="2026-05-05T01:00:00Z",
        )
    )

    result = call(provider, "continuity_dream", {"mode": "archive-safe"})

    assert result["success"] is True
    assert result["mode"] == "archive-safe"
    assert result["mutated"] is True
    assert result["archived_ids"] == ["old_state"]
    assert provider._store.get_record("old_state").status == "archived"  # type: ignore[union-attr]
    assert provider._store.get_state("dream:last_run_at") is not None


def test_due_scheduled_dream_runs_on_turn_when_enabled(tmp_path: Path) -> None:
    provider = initialized_provider(
        tmp_path,
        dream={
            "enabled": True,
            "schedule": "00:00",
            "timezone": "UTC",
            "mode": "archive-safe",
            "run_on_initialize": False,
            "run_on_turn": True,
        },
    )
    assert provider._store is not None
    provider._store.upsert_record(
        make_project_state(
            "old_state",
            summary="continuity old noisy graph status",
            updated_at="2026-05-04T01:00:00Z",
        )
    )
    provider._store.upsert_record(
        make_project_state(
            "new_state",
            summary="continuity new facet-gated graph status",
            updated_at="2026-05-05T01:00:00Z",
        )
    )

    provider._maybe_run_scheduled_dream(now=datetime(2026, 5, 5, 0, 1, tzinfo=UTC))

    assert provider._store.get_record("old_state").status == "archived"  # type: ignore[union-attr]
    assert provider._store.get_state("dream:last_run_at") is not None
