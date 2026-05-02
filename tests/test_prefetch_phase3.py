from __future__ import annotations

import json
from pathlib import Path

from continuity import ContinuityProvider
from continuity.models import ContextRecord, SourceRef
from continuity.store import ContinuityStore


def seed_prefetch_records(store: ContinuityStore) -> None:
    store.upsert_record(
        ContextRecord.new(
            id="r_delegate_timeout",
            kind="lesson_learned",
            scope_project="guard-proxy",
            title="delegate_task timeout before API calls",
            summary="delegate_task can return status:timeout with api_calls:0 after exactly 300s; repeated delegation is usually wasteful, so work inline.",
            tags=["delegate_task", "timeout", "hermes"],
            entities=["api_calls:0", "300s"],
            sources=[SourceRef(type="session", id="s1", range="turns 44-59")],
            confidence=0.95,
            importance=0.9,
        )
    )
    store.upsert_record(
        ContextRecord.new(
            id="r_llama_systemd",
            kind="environment_fact",
            scope_project="llama-server",
            title="GH200 has no installed llama-server systemd service",
            summary="No installed llama-server.service was present on GH200.",
            tags=["systemd", "llama-server"],
            entities=["llama-server.service"],
            confidence=0.9,
            importance=0.65,
        )
    )


def initialized_provider(tmp_path: Path, *, max_chars: int = 1800) -> ContinuityProvider:
    provider = ContinuityProvider()
    provider.initialize(
        session_id="session-123",
        hermes_home=str(tmp_path),
        continuity_config={"max_chars": max_chars, "max_records": 3},
    )
    assert provider._store is not None
    seed_prefetch_records(provider._store)
    return provider


def test_prefetch_returns_compact_relevant_context_under_budget(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path)

    result = provider.prefetch(
        "the subagent timed out without doing anything again",
        scope_project="guard-proxy",
    )

    assert result.startswith("Relevant continuity memory:")
    assert "delegate_task can return status:timeout" in result
    assert "Sources: session:s1 turns 44-59" in result
    assert "llama-server" not in result
    assert len(result) <= 1800


def test_prefetch_returns_empty_string_when_no_record_matches(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path)

    assert provider.prefetch("totally unrelated banana question", scope_project="guard-proxy") == ""


def test_prefetch_obeys_max_chars_without_partial_records(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path, max_chars=220)

    result = provider.prefetch("subagent timeout api_calls:0", scope_project="guard-proxy")

    assert len(result) <= 220
    assert result == "" or result.endswith("turns 44-59")


def test_prefetch_logs_retrieval_event(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path)

    provider.prefetch("subagent timeout api_calls:0", scope_project="guard-proxy")

    assert provider._store is not None
    event = provider._store.last_retrieval_event()
    assert event is not None
    assert event["query"] == "subagent timeout api_calls:0"
    assert json.loads(event["selected_ids_json"]) == ["r_delegate_timeout"]
    scores = json.loads(event["scores_json"])
    assert scores["r_delegate_timeout"] > 0
