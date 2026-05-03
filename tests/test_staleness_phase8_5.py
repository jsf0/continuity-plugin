from __future__ import annotations

import json
from pathlib import Path

from continuity import ContinuityProvider
from continuity.models import ContextRecord
from continuity.retrieval import ContinuityRetriever
from continuity.store import ContinuityStore


def make_record(
    record_id: str,
    *,
    summary: str,
    kind: str = "lesson_learned",
    scope_project: str | None = "guard-proxy",
    created_at: str = "2026-01-01T00:00:00Z",
    updated_at: str = "2026-01-01T00:00:00Z",
    status: str = "active",
    superseded_by: str | None = None,
    stale_reason: str | None = None,
    archived_at: str | None = None,
    expires_at: str | None = None,
) -> ContextRecord:
    return ContextRecord.from_dict(
        {
            "id": record_id,
            "kind": kind,
            "scope_project": scope_project,
            "title": "guard-proxy status",
            "summary": summary,
            "tags": ["guard-proxy", "status"],
            "entities": ["guard-proxy"],
            "confidence": 0.9,
            "importance": 0.8,
            "trust_level": "agent_observed",
            "created_at": created_at,
            "updated_at": updated_at,
            "status": status,
            "superseded_by": superseded_by,
            "stale_reason": stale_reason,
            "archived_at": archived_at,
            "expires_at": expires_at,
        }
    )


def initialized_provider(tmp_path: Path) -> ContinuityProvider:
    provider = ContinuityProvider()
    provider.initialize(session_id="staleness-phase8-5", hermes_home=str(tmp_path))
    return provider


def call(
    provider: ContinuityProvider, tool_name: str, args: dict[str, object]
) -> dict[str, object]:
    return json.loads(provider.handle_tool_call(tool_name, args))


def test_retriever_excludes_archived_and_expired_records_by_default(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(
        make_record(
            "r_archived",
            summary="guard-proxy stale archived SPKI docs memory",
            status="archived",
            stale_reason="superseded by newer project state",
            archived_at="2026-02-01T00:00:00Z",
        )
    )
    store.upsert_record(
        make_record(
            "r_expired",
            summary="guard-proxy expired SPKI docs memory",
            expires_at="2020-01-01T00:00:00Z",
        )
    )
    store.upsert_record(make_record("r_active", summary="guard-proxy current SPKI docs memory"))

    default_hits = ContinuityRetriever(store).search("guard-proxy SPKI docs", limit=10)
    default_ids = [hit.record.id for hit in default_hits]
    assert default_ids == ["r_active"]

    stale_hits = ContinuityRetriever(store).search(
        "guard-proxy SPKI docs", limit=10, include_stale=True
    )
    assert {hit.record.id for hit in stale_hits} == {"r_active", "r_archived", "r_expired"}


def test_store_can_archive_and_restore_records(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.upsert_record(make_record("r_old", summary="old guard-proxy status"))

    archived = store.archive_record("r_old", reason="superseded by r_new", superseded_by="r_new")
    assert archived is True
    record = store.get_record("r_old")
    assert record is not None
    assert record.status == "archived"
    assert record.stale_reason == "superseded by r_new"
    assert record.superseded_by == "r_new"
    assert record.archived_at is not None

    restored = store.restore_record("r_old")
    assert restored is True
    record = store.get_record("r_old")
    assert record is not None
    assert record.status == "active"
    assert record.stale_reason is None
    assert record.superseded_by is None
    assert record.archived_at is None


def test_prune_stale_dry_run_reports_older_project_state_without_mutating(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path)
    assert provider._store is not None
    provider._store.upsert_record(
        make_record(
            "r_old_state",
            kind="active_project_state",
            summary="guard-proxy old head cc78de9",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
    )
    provider._store.upsert_record(
        make_record(
            "r_new_state",
            kind="active_project_state",
            summary="guard-proxy current head 4fd241e",
            created_at="2026-02-01T00:00:00Z",
            updated_at="2026-02-01T00:00:00Z",
        )
    )

    result = call(provider, "continuity_prune_stale", {"dry_run": True})

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["mode"] == "archive"
    assert [candidate["id"] for candidate in result["candidates"]] == ["r_old_state"]
    assert result["candidates"][0]["superseded_by"] == "r_new_state"
    assert provider._store.get_record("r_old_state").status == "active"  # type: ignore[union-attr]


def test_prune_stale_archive_marks_older_project_state_and_excludes_from_search(
    tmp_path: Path,
) -> None:
    provider = initialized_provider(tmp_path)
    assert provider._store is not None
    provider._store.upsert_record(
        make_record(
            "r_old_state",
            kind="active_project_state",
            summary="guard-proxy old head cc78de9",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
    )
    provider._store.upsert_record(
        make_record(
            "r_new_state",
            kind="active_project_state",
            summary="guard-proxy current head 4fd241e",
            created_at="2026-02-01T00:00:00Z",
            updated_at="2026-02-01T00:00:00Z",
        )
    )

    result = call(provider, "continuity_prune_stale", {"dry_run": False, "mode": "archive"})

    assert result["success"] is True
    assert result["archived_ids"] == ["r_old_state"]
    old_record = provider._store.get_record("r_old_state")
    assert old_record is not None
    assert old_record.status == "archived"
    assert old_record.superseded_by == "r_new_state"

    search_result = call(provider, "continuity_search", {"query": "guard-proxy head", "limit": 10})
    assert [item["id"] for item in search_result["results"]] == ["r_new_state"]


def test_archive_and_restore_tools_control_retrieval_visibility(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path)
    assert provider._store is not None
    provider._store.upsert_record(make_record("r_visible", summary="guard-proxy visible memory"))

    archived = call(
        provider,
        "continuity_archive",
        {"id": "r_visible", "reason": "no longer relevant"},
    )
    assert archived["success"] is True
    assert archived["archived"] is True
    assert call(provider, "continuity_search", {"query": "visible memory"})["results"] == []

    restored = call(provider, "continuity_restore", {"id": "r_visible"})
    assert restored["success"] is True
    assert restored["restored"] is True
    assert (
        call(provider, "continuity_search", {"query": "visible memory"})["results"][0]["id"]
        == "r_visible"
    )
