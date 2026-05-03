from __future__ import annotations

import json
from pathlib import Path

from continuity import ContinuityProvider


def test_vector_config_enables_provider_indexing_and_search(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "guard-proxy"
    project_dir.mkdir()
    monkeypatch.setenv("TERMINAL_CWD", str(project_dir))
    provider = ContinuityProvider()
    provider.initialize(
        session_id="vector-session",
        hermes_home=str(tmp_path / "hermes"),
        continuity_config={
            "consolidate_min_turns": 1,
            "vector": {"enabled": True, "backend": "sqlite-hash"},
        },
    )

    add_payload = json.loads(
        provider.handle_tool_call(
            "continuity_add",
            {
                "id": "r_delegate_timeout",
                "kind": "lesson_learned",
                "title": "delegate_task timeout",
                "summary": "delegate_task can time out after 300s with api_calls:0.",
                "scope_project": "guard-proxy",
                "tags": ["delegate_task", "timeout"],
            },
        )
    )
    assert add_payload["success"] is True

    status = json.loads(provider.handle_tool_call("continuity_status", {}))
    assert status["phase"] == "phase-8.5-stale-memory-lifecycle"
    assert status["vector_enabled"] is True
    assert status["vector_available"] is True
    assert status["vector_count"] == 1

    search_payload = json.loads(
        provider.handle_tool_call(
            "continuity_search",
            {"query": "subagent hung", "scope_project": "guard-proxy", "limit": 3},
        )
    )
    assert search_payload["success"] is True
    assert search_payload["results"][0]["id"] == "r_delegate_timeout"
    assert "vector" in search_payload["results"][0]["reasons"]


def test_vector_delete_removes_index_row(tmp_path: Path) -> None:
    provider = ContinuityProvider()
    provider.initialize(
        session_id="vector-delete",
        hermes_home=str(tmp_path / "hermes"),
        continuity_config={"vector": {"enabled": True, "backend": "sqlite-hash"}},
    )
    provider.handle_tool_call(
        "continuity_add",
        {
            "id": "r_delete_me",
            "kind": "decision",
            "title": "delete me",
            "summary": "Temporary vector-indexed record.",
        },
    )

    before = json.loads(provider.handle_tool_call("continuity_status", {}))
    assert before["vector_count"] == 1
    delete_payload = json.loads(
        provider.handle_tool_call("continuity_delete", {"id": "r_delete_me"})
    )
    after = json.loads(provider.handle_tool_call("continuity_status", {}))

    assert delete_payload == {"success": True, "deleted": True, "id": "r_delete_me"}
    assert after["vector_count"] == 0
