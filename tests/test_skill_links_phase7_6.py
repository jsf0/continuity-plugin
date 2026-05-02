from __future__ import annotations

import json
from pathlib import Path

from continuity import ContinuityProvider
from continuity.models import ContextRecord, SkillLink
from continuity.store import ContinuityStore


def test_skill_link_model_validates_and_round_trips() -> None:
    link = SkillLink(
        record_id="r_delegate_timeout",
        skill_name="software-development/systematic-debugging",
        reason="Relevant when debugging recurring timeout failures.",
        confidence=0.9,
        source="explicit_user",
    )

    assert SkillLink.from_dict(link.to_dict()) == link


def test_store_persists_lists_replaces_and_deletes_skill_links(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    record = ContextRecord.new(
        id="r_delegate_timeout",
        kind="lesson_learned",
        title="delegate timeout",
        summary="delegate_task can time out.",
    )
    store.upsert_record(record)
    link = SkillLink(
        record_id=record.id,
        skill_name="software-development/systematic-debugging",
        reason="Use when investigating timeout failures.",
        confidence=0.85,
        source="agent_observed",
    )

    store.upsert_skill_link(link)
    assert store.list_skill_links(record.id) == [link]

    replacement = SkillLink(
        record_id=record.id,
        skill_name="devops/openbsd-rust-dev-loop",
        reason="Use when validating Rust behavior on OpenBSD.",
        confidence=0.75,
        source="explicit_user",
    )
    store.replace_skill_links(record.id, [replacement])
    assert store.list_skill_links(record.id) == [replacement]

    store.delete_record(record.id)
    assert store.list_skill_links(record.id) == []


def initialized_provider(tmp_path: Path) -> ContinuityProvider:
    provider = ContinuityProvider()
    provider.initialize(
        session_id="skill-link-session",
        hermes_home=str(tmp_path / "hermes"),
        continuity_config={"max_records": 3, "max_chars": 1800},
    )
    return provider


def test_continuity_add_get_and_search_include_skill_links(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path)

    add_payload = json.loads(
        provider.handle_tool_call(
            "continuity_add",
            {
                "id": "r_delegate_timeout",
                "kind": "lesson_learned",
                "title": "delegate_task timeout",
                "summary": "delegate_task can time out before subagents report API calls.",
                "tags": ["delegate_task", "timeout"],
                "skill_links": [
                    {
                        "skill_name": "software-development/systematic-debugging",
                        "reason": "Use when debugging recurring timeout failures.",
                        "confidence": 0.9,
                        "source": "explicit_user",
                    }
                ],
            },
        )
    )

    assert add_payload["success"] is True
    assert add_payload["record"]["id"] == "r_delegate_timeout"
    assert (
        add_payload["skill_links"][0]["skill_name"] == "software-development/systematic-debugging"
    )

    get_payload = json.loads(
        provider.handle_tool_call("continuity_get", {"id": "r_delegate_timeout"})
    )
    assert get_payload["success"] is True
    assert (
        get_payload["skill_links"][0]["reason"] == "Use when debugging recurring timeout failures."
    )

    search_payload = json.loads(
        provider.handle_tool_call("continuity_search", {"query": "delegate timeout", "limit": 3})
    )
    assert search_payload["success"] is True
    assert (
        search_payload["results"][0]["skill_links"][0]["skill_name"]
        == "software-development/systematic-debugging"
    )


def test_prefetch_includes_budgeted_related_skill_hint(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path)
    add_payload = json.loads(
        provider.handle_tool_call(
            "continuity_add",
            {
                "id": "r_openbsd_lint",
                "kind": "lesson_learned",
                "title": "OpenBSD Rust lint gotcha",
                "summary": "patch lint can falsely report Rust 2015 async errors; verify with cargo check.",
                "scope_project": "guard-proxy",
                "tags": ["openbsd", "rust", "lint"],
                "skill_links": [
                    {
                        "skill_name": "devops/openbsd-rust-dev-loop",
                        "reason": "Relevant for OpenBSD Rust verification.",
                        "confidence": 0.95,
                    },
                    {
                        "skill_name": "software-development/systematic-debugging",
                        "reason": "Secondary fallback.",
                        "confidence": 0.4,
                    },
                ],
            },
        )
    )
    assert add_payload["success"] is True

    output = provider.prefetch("patch lint Rust 2015 cargo check", scope_project="guard-proxy")

    assert "Related skills: devops/openbsd-rust-dev-loop" in output
    assert "software-development/systematic-debugging" not in output


def test_continuity_delete_removes_skill_links(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path)
    assert provider._store is not None
    provider.handle_tool_call(
        "continuity_add",
        {
            "id": "r_delete_skill_link",
            "kind": "decision",
            "title": "delete linked record",
            "summary": "Temporary linked record.",
            "skill_links": [{"skill_name": "github/github-pr-workflow", "confidence": 0.8}],
        },
    )
    assert provider._store.list_skill_links("r_delete_skill_link")

    delete_payload = json.loads(
        provider.handle_tool_call("continuity_delete", {"id": "r_delete_skill_link"})
    )

    assert delete_payload["success"] is True
    assert provider._store.list_skill_links("r_delete_skill_link") == []
