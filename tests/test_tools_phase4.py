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
        "continuity_hydrate",
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


def test_continuity_quality_report_can_recompute_and_apply_quality_backfill(
    tmp_path: Path,
) -> None:
    provider = initialized_provider(tmp_path)
    call(
        provider,
        "continuity_add",
        {
            "id": "r_quality_backfill_tool",
            "kind": "lesson_learned",
            "title": "Notes",
            "summary": "Use documented retry behavior when the worker queue stalls.",
            "details": "Quality diagnostics must stay out of retrieval content.",
            "tags": [],
            "entities": [],
            "trust_level": "corpus_distilled",
        },
    )
    assert provider._store is not None
    with provider._store.connect() as conn:
        conn.execute(
            "UPDATE context_records SET quality_json = '{}' WHERE id = ?",
            ("r_quality_backfill_tool",),
        )
        before = conn.execute(
            """
            SELECT summary, details, tags_json, entities_json, embedding_text, quality_json
            FROM context_records WHERE id = ?
            """,
            ("r_quality_backfill_tool",),
        ).fetchone()

    report_only = call(
        provider,
        "continuity_quality_report",
        {"limit": 10, "recompute": True, "apply_backfill": False},
    )
    after_report_only = provider._store.get_record("r_quality_backfill_tool")

    assert report_only["success"] is True
    assert report_only["mode"] == "recompute"
    assert report_only["counts"]["drift_records"] == 1
    assert report_only["updated_count"] == 0
    assert after_report_only is not None
    assert after_report_only.quality == {}

    applied = call(
        provider,
        "continuity_quality_report",
        {"limit": 10, "recompute": True, "apply_backfill": True},
    )
    with provider._store.connect() as conn:
        after = conn.execute(
            """
            SELECT summary, details, tags_json, entities_json, embedding_text, quality_json
            FROM context_records WHERE id = ?
            """,
            ("r_quality_backfill_tool",),
        ).fetchone()

    assert applied["success"] is True
    assert applied["mode"] == "recompute"
    assert applied["counts"]["drift_records"] == 0
    assert applied["updated_count"] == 1
    assert dict(before)["summary"] == dict(after)["summary"]
    assert dict(before)["details"] == dict(after)["details"]
    assert dict(before)["tags_json"] == dict(after)["tags_json"]
    assert dict(before)["entities_json"] == dict(after)["entities_json"]
    assert dict(before)["embedding_text"] == dict(after)["embedding_text"]
    assert dict(after)["quality_json"] != "{}"


def test_debug_retrieval_includes_plain_english_tuning_advice(tmp_path: Path) -> None:
    provider = ContinuityProvider()
    provider.initialize(
        session_id="debug-advice",
        hermes_home=str(tmp_path),
        continuity_config={"retrieval_gates": {"min_base_relevance": 2.0}},
    )
    call(
        provider,
        "continuity_add",
        {
            "id": "r_soft_debug_match",
            "kind": "lesson_learned",
            "title": "soft debug match",
            "summary": "zebra appears once in this otherwise generic note.",
        },
    )

    debug = call(provider, "continuity_debug_retrieval", {"query": "zebra", "limit": 3})

    assert debug["success"] is True
    rejected = {item["id"]: item for item in debug["rejected"]}
    assert rejected["r_soft_debug_match"]["rejected_reason"] == "below_min_base_relevance"
    assert rejected["r_soft_debug_match"]["tuning_advice"]["config"] == (
        "retrieval_gates.min_base_relevance"
    )
    assert "lower" in rejected["r_soft_debug_match"]["tuning_advice"]["try"].lower()
    assert debug["tuning_advice"][0]["reason"] == "below_min_base_relevance"
