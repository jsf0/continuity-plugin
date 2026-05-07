from __future__ import annotations

import json
from pathlib import Path

from continuity import ContinuityProvider
from continuity.models import ContextRecord


def test_system_prompt_block_renders_pinned_high_importance_records(tmp_path: Path) -> None:
    provider = ContinuityProvider()
    provider.initialize(
        session_id="pinned-phase9",
        hermes_home=str(tmp_path),
        continuity_config={
            "pinned_system_prompt": {
                "enabled": True,
                "max_chars": 400,
                "kinds": ["user_preference", "project_convention"],
                "min_importance": 0.75,
                "max_records": 3,
            }
        },
    )
    assert provider._store is not None
    provider._store.upsert_record(
        ContextRecord.new(
            id="r_pref",
            kind="user_preference",
            title="Work mode",
            summary="Joseph prefers methodical, thorough, correct work with tests before done.",
            importance=0.95,
            confidence=0.95,
            trust_level="explicit_user",
        )
    )
    provider._store.upsert_record(
        ContextRecord.new(
            id="r_low",
            kind="lesson_learned",
            title="Low value",
            summary="This should not be pinned.",
            importance=0.4,
            confidence=0.9,
        )
    )

    block = provider.system_prompt_block()

    assert "CONTINUITY PINNED MEMORY" in block
    assert "methodical, thorough, correct" in block
    assert "This should not be pinned" not in block


def test_pinned_system_prompt_is_enabled_by_default(tmp_path: Path) -> None:
    provider = ContinuityProvider()
    provider.initialize(
        session_id="pinned-default",
        hermes_home=str(tmp_path),
        continuity_config={},
    )
    assert provider._store is not None
    provider._store.upsert_record(
        ContextRecord.new(
            id="r_default_pin",
            kind="user_preference",
            title="Work mode",
            summary="Joseph prefers continuity tier zero memory to replace stock memory.",
            importance=0.95,
            confidence=0.95,
            trust_level="explicit_user",
        )
    )

    block = provider.system_prompt_block()

    assert "CONTINUITY PINNED MEMORY" in block
    assert "tier zero memory" in block


def test_system_prompt_block_includes_continuity_guidance_when_pinning_disabled(
    tmp_path: Path,
) -> None:
    provider = ContinuityProvider()
    provider.initialize(
        session_id="guidance-phase9",
        hermes_home=str(tmp_path),
        continuity_config={"pinned_system_prompt": {"enabled": False}},
    )

    block = provider.system_prompt_block()

    assert "CONTINUITY MEMORY PROVIDER" in block
    assert "Routine memory writes: use the memory tool" in block
    assert "Routine memory recall: read any provided <memory-context> first" in block
    assert "use continuity_status, continuity_search, or continuity_debug_retrieval" in block
    assert "When asked whether continuity helped" in block
    assert "inspect recent retrieval events" in block
    assert "Do not retrieve against quoted prior assistant text" in block
    assert "empty or noisy retrieval is not proof of absence" in block
    assert "try both 'ldomctl' and 'ldomctl OpenBSD logical domains'" in block
    assert "continuity_hydrate takes a continuity record id" in block
    assert "not a corpus segment id such as 'seg_...'" in block
    assert "continuity_hydrate before claiming the source is absent" in block
    assert "use continuity_debug_retrieval to inspect selected/rejected" in block
    assert "do not load the hermes-continuity-memory skill for ordinary memory recall" in block


def test_system_prompt_block_guidance_only_mode_omits_record_summaries(tmp_path: Path) -> None:
    provider = ContinuityProvider()
    provider.initialize(
        session_id="guidance-only-phase9",
        hermes_home=str(tmp_path),
        continuity_config={
            "pinned_system_prompt": {
                "enabled": True,
                "include_records": False,
            }
        },
    )
    assert provider._store is not None
    provider._store.upsert_record(
        ContextRecord.new(
            id="r_private_pref",
            kind="user_preference",
            title="Private preference",
            summary="This durable preference must not appear in guidance-only mode.",
            importance=1.0,
            confidence=1.0,
            trust_level="explicit_user",
        )
    )

    block = provider.system_prompt_block()

    assert "CONTINUITY MEMORY PROVIDER" in block
    assert "CONTINUITY PINNED MEMORY" not in block
    assert "This durable preference must not appear" not in block


def test_system_prompt_block_skips_archived_records(tmp_path: Path) -> None:
    provider = ContinuityProvider()
    provider.initialize(
        session_id="pinned-phase9",
        hermes_home=str(tmp_path),
        continuity_config={"pinned_system_prompt": {"enabled": True}},
    )
    assert provider._store is not None
    provider._store.upsert_record(
        ContextRecord.from_dict(
            {
                "id": "r_archived_pref",
                "kind": "user_preference",
                "title": "Archived preference",
                "summary": "Archived preferences should not be pinned.",
                "importance": 1.0,
                "confidence": 1.0,
                "status": "archived",
            }
        )
    )

    block = provider.system_prompt_block()

    assert "CONTINUITY MEMORY PROVIDER" in block
    assert "Archived preferences should not be pinned" not in block


def test_continuity_status_reports_pinned_prompt_config(tmp_path: Path) -> None:
    provider = ContinuityProvider()
    provider.initialize(
        session_id="pinned-phase9",
        hermes_home=str(tmp_path),
        continuity_config={
            "pinned_system_prompt": {
                "enabled": True,
                "include_records": False,
                "max_chars": 777,
            }
        },
    )

    status = json.loads(provider.handle_tool_call("continuity_status", {}))

    assert status["pinned_system_prompt_enabled"] is True
    assert status["pinned_system_prompt_include_records"] is False
    assert status["pinned_system_prompt_max_chars"] == 777
