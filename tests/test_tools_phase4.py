from __future__ import annotations

import json
from pathlib import Path

from continuity import ContinuityProvider


def initialized_provider(tmp_path: Path) -> ContinuityProvider:
    provider = ContinuityProvider()
    provider.initialize(session_id="tools-phase4", hermes_home=str(tmp_path))
    return provider


def call(
    provider: ContinuityProvider, tool_name: str, args: dict[str, object]
) -> dict[str, object]:
    return json.loads(provider.handle_tool_call(tool_name, args))


def test_phase4_provider_exposes_search_get_add_delete_status_tools() -> None:
    provider = ContinuityProvider()

    names = {schema["name"] for schema in provider.get_tool_schemas()}

    assert names == {
        "continuity_status",
        "continuity_search",
        "continuity_get",
        "continuity_add",
        "continuity_delete",
        "continuity_archive",
        "continuity_restore",
        "continuity_prune_stale",
        "continuity_debug_retrieval",
        "continuity_association_edges",
        "continuity_reindex_vectors",
        "continuity_dream",
        "continuity_quality_report",
    }


def test_add_get_search_delete_record_tool_flow(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path)

    added = call(
        provider,
        "continuity_add",
        {
            "id": "r_tool_delegate",
            "kind": "lesson_learned",
            "title": "delegate_task timeout",
            "summary": "delegate_task can return status:timeout with api_calls:0 after exactly 300s.",
            "scope_project": "guard-proxy",
            "tags": ["delegate_task", "timeout"],
            "entities": ["api_calls:0", "300s"],
            "sources": [{"type": "session", "id": "s1", "range": "turns 1-2"}],
            "confidence": 0.95,
            "importance": 0.9,
        },
    )

    assert added["success"] is True
    assert added["record"]["id"] == "r_tool_delegate"

    fetched = call(provider, "continuity_get", {"id": "r_tool_delegate"})
    assert fetched["success"] is True
    assert fetched["record"]["summary"].startswith("delegate_task can return")

    searched = call(
        provider, "continuity_search", {"query": "subagent timeout api_calls:0", "limit": 3}
    )
    assert searched["success"] is True
    assert searched["results"][0]["id"] == "r_tool_delegate"
    assert searched["results"][0]["score"] > 0
    assert "reasons" in searched["results"][0]

    status = call(provider, "continuity_status", {})
    assert status["record_count"] == 1

    deleted = call(provider, "continuity_delete", {"id": "r_tool_delegate"})
    assert deleted["success"] is True
    assert deleted["deleted"] is True

    missing = call(provider, "continuity_get", {"id": "r_tool_delegate"})
    assert missing["success"] is False
    assert "not found" in missing["error"]


def test_add_tool_validates_required_fields(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path)

    result = call(
        provider, "continuity_add", {"kind": "lesson_learned", "summary": "missing title"}
    )

    assert result["success"] is False
    assert "title" in result["error"]


def test_tools_are_safe_before_initialize() -> None:
    provider = ContinuityProvider()

    for tool_name, args in [
        ("continuity_search", {"query": "timeout"}),
        ("continuity_get", {"id": "r1"}),
        ("continuity_add", {"kind": "lesson_learned", "title": "t", "summary": "s"}),
        ("continuity_delete", {"id": "r1"}),
    ]:
        result = call(provider, tool_name, args)
        assert result["success"] is False
        assert "not initialized" in result["error"]


def test_search_tool_validates_query(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path)

    result = call(provider, "continuity_search", {"query": ""})

    assert result["success"] is False
    assert "query" in result["error"]


def test_continuity_add_enriches_literal_metadata_before_storage(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path)

    payload = call(
        provider,
        "continuity_add",
        {
            "id": "r_manual_enriched",
            "kind": "project_convention",
            "title": "OpenBSD guard-proxy deployment",
            "summary": "guard-proxy deployment uses tag:openbsd and rcctl restart.",
            "tags": ["deployment"],
            "entities": [],
            "trust_level": "explicit_user",
        },
    )

    assert payload["success"] is True
    record = payload["record"]
    assert "openbsd" in record["tags"]
    assert "guard-proxy" in record["entities"]
    assert record["quality"]["score"] <= 1.0


def test_continuity_quality_report_returns_warning_records(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path)
    call(
        provider,
        "continuity_add",
        {
            "id": "r_quality_report_sparse",
            "kind": "user_preference",
            "title": "Sparse preference",
            "summary": "User prefers concise replies.",
            "tags": ["user_preference"],
            "entities": [],
            "trust_level": "explicit_user",
        },
    )

    payload = call(provider, "continuity_quality_report", {"limit": 10})

    assert payload["success"] is True
    assert any(item["id"] == "r_quality_report_sparse" for item in payload["records"])
