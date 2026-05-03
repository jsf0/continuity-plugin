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

    assert provider.system_prompt_block() == ""


def test_continuity_status_reports_pinned_prompt_config(tmp_path: Path) -> None:
    provider = ContinuityProvider()
    provider.initialize(
        session_id="pinned-phase9",
        hermes_home=str(tmp_path),
        continuity_config={"pinned_system_prompt": {"enabled": True, "max_chars": 777}},
    )

    status = json.loads(provider.handle_tool_call("continuity_status", {}))

    assert status["pinned_system_prompt_enabled"] is True
    assert status["pinned_system_prompt_max_chars"] == 777
