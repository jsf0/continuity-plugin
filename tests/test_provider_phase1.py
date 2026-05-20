from __future__ import annotations

import json
from pathlib import Path

from continuity import ContinuityProvider, register
from continuity.models import ContextRecord


class ProviderCollector:
    def __init__(self) -> None:
        self.provider = None

    def register_memory_provider(self, provider: object) -> None:
        self.provider = provider


def test_register_exposes_continuity_provider() -> None:
    collector = ProviderCollector()

    register(collector)

    assert isinstance(collector.provider, ContinuityProvider)
    assert collector.provider.name == "continuity"
    assert collector.provider.is_available() is True


def test_initialize_creates_data_directory_and_status(tmp_path: Path) -> None:
    provider = ContinuityProvider()

    provider.initialize(
        session_id="session-123",
        hermes_home=str(tmp_path),
        platform="pytest",
        agent_context="primary",
    )
    result = json.loads(provider.handle_tool_call("continuity_status", {}))

    assert result["success"] is True
    assert result["initialized"] is True
    assert result["provider"] == "continuity"
    assert result["session_id"] == "session-123"
    assert result["hermes_home"] == str(tmp_path)
    assert result["data_dir"] == str(tmp_path / "continuity")
    assert Path(result["data_dir"]).is_dir()
    assert result["record_count"] == 0
    assert result["vector_enabled"] is False


def test_status_tool_is_safe_before_initialize() -> None:
    provider = ContinuityProvider()

    result = json.loads(provider.handle_tool_call("continuity_status", {}))

    assert result["success"] is True
    assert result["initialized"] is False
    assert result["provider"] == "continuity"
    assert result["data_dir"] is None


def test_unknown_tool_returns_json_error() -> None:
    provider = ContinuityProvider()

    result = json.loads(provider.handle_tool_call("continuity_missing", {}))

    assert result["success"] is False
    assert "Unknown continuity tool" in result["error"]


def test_phase1_prefetch_is_noop_until_retrieval_phase(tmp_path: Path) -> None:
    provider = ContinuityProvider()
    provider.initialize(session_id="session-123", hermes_home=str(tmp_path))

    assert provider.prefetch("delegate timeout") == ""


def test_status_reports_retrieval_gate_config(tmp_path: Path) -> None:
    provider = ContinuityProvider()
    provider.initialize(
        session_id="session-gates",
        hermes_home=str(tmp_path),
        continuity_config={
            "retrieval_gates": {
                "min_base_relevance": 0.2,
                "low_information": False,
            }
        },
    )

    result = json.loads(provider.handle_tool_call("continuity_status", {}))

    assert result["retrieval_gates"]["min_base_relevance"] == 0.2
    assert result["retrieval_gates"]["min_vector_relevance"] == 0.05
    assert result["retrieval_gates"]["low_information"] is False
    assert result["retrieval_gates"]["facet_compatibility"] is True


class CapturingStore:
    def __init__(self) -> None:
        self.upsert_kwargs: dict[str, object] | None = None

    def upsert_record(self, record: ContextRecord, **kwargs: object) -> None:
        self.upsert_kwargs = kwargs


def test_provider_upsert_disables_association_creation_when_graph_disabled(tmp_path: Path) -> None:
    provider = ContinuityProvider()
    provider.initialize(
        session_id="session-association-disabled",
        hermes_home=str(tmp_path),
        continuity_config={"association_graph": {"enabled": False}},
    )
    store = CapturingStore()
    provider._store = store  # type: ignore[assignment]

    provider._upsert_record(
        ContextRecord.new(
            id="record-1",
            kind="environment_fact",
            title="Record one",
            summary="A record that should not create associations when disabled.",
        )
    )

    assert store.upsert_kwargs is not None
    assert store.upsert_kwargs["create_associations"] is False

