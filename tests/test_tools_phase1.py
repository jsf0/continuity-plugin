from __future__ import annotations

import json

from continuity import CONTINUITY_STATUS_SCHEMA, ContinuityProvider


def test_status_tool_schema_is_openai_function_shape() -> None:
    schema = CONTINUITY_STATUS_SCHEMA

    assert schema["name"] == "continuity_status"
    assert isinstance(schema["description"], str)
    assert schema["parameters"]["type"] == "object"
    assert schema["parameters"]["required"] == []


def test_provider_exposes_phase4_tool_schemas() -> None:
    provider = ContinuityProvider()

    names = {schema["name"] for schema in provider.get_tool_schemas()}

    assert CONTINUITY_STATUS_SCHEMA in provider.get_tool_schemas()
    assert names == {
        "continuity_status",
        "continuity_search",
        "continuity_get",
        "continuity_hydrate",
        "continuity_add",
        "continuity_delete",
        "continuity_archive",
        "continuity_restore",
        "continuity_prune_stale",
        "continuity_debug_retrieval",
        "continuity_recent_retrievals",
        "continuity_association_edges",
        "continuity_rebuild_associations",
        "continuity_reindex_vectors",
        "continuity_dream",
        "continuity_quality_report",
    }


def test_recent_retrievals_tool_reports_bounded_event_history(tmp_path) -> None:
    provider = ContinuityProvider()
    provider.initialize(session_id="recent-retrievals", hermes_home=str(tmp_path))
    assert provider._store is not None
    provider._store.log_retrieval_event(
        query="how do i configure OpenBSD to use ldapd with sshd sessions",
        selected_ids=["ldapd_files"],
        skipped_ids=["unrelated"],
        scores={"ldapd_files": 5.9},
        max_chars=1800,
    )

    payload = json.loads(provider.handle_tool_call("continuity_recent_retrievals", {"limit": 3}))

    assert payload["success"] is True
    assert (
        payload["events"][0]["query"]
        == "how do i configure OpenBSD to use ldapd with sshd sessions"
    )
    assert payload["events"][0]["selected_ids"] == ["ldapd_files"]
    assert payload["events"][0]["skipped_ids"] == ["unrelated"]
    assert payload["events"][0]["scores"] == {"ldapd_files": 5.9}
