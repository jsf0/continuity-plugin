from __future__ import annotations

from pathlib import Path

from continuity import ContinuityProvider


def initialized_provider(tmp_path: Path, *, min_turns: int = 2) -> ContinuityProvider:
    provider = ContinuityProvider()
    provider.initialize(
        session_id="phase5-session",
        hermes_home=str(tmp_path),
        continuity_config={"consolidate_min_turns": min_turns},
    )
    return provider


def test_sync_turn_persists_observation_when_enabled(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path)
    assert provider._store is not None

    provider.sync_turn("Remember: I prefer concise answers.", "Noted.", session_id="phase5-session")

    observations = provider._store.list_unconsolidated_observations("phase5-session")
    assert len(observations) == 1
    assert "concise answers" in observations[0]["user_content"]


def test_on_session_end_consolidates_records_and_marks_observations(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path, min_turns=1)
    assert provider._store is not None

    provider.sync_turn("Remember: I prefer foundation-first sequencing.", "Noted.", session_id="phase5-session")
    provider.on_session_end(
        [
            {"role": "user", "content": "Remember: I prefer foundation-first sequencing."},
            {"role": "assistant", "content": "Lesson learned: delegate_task can timeout with api_calls:0."},
        ]
    )

    records = provider._store.list_records()
    summaries = "\n".join(record.summary for record in records)
    assert "foundation-first" in summaries
    assert "delegate_task" in summaries
    assert provider._store.list_unconsolidated_observations("phase5-session") == []


def test_on_session_end_dedupes_repeated_records(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path, min_turns=1)
    assert provider._store is not None
    messages = [
        {"role": "user", "content": "Remember: I prefer foundation-first sequencing."},
        {"role": "assistant", "content": "Noted."},
    ]

    provider.on_session_end(messages)
    provider.on_session_end(messages)

    records = provider._store.list_records()
    matching = [record for record in records if "foundation-first" in record.summary]
    assert len(matching) == 1


def test_on_session_end_skips_short_sessions_by_default(tmp_path: Path) -> None:
    provider = initialized_provider(tmp_path, min_turns=3)
    assert provider._store is not None

    provider.on_session_end([
        {"role": "user", "content": "Remember: I prefer foundation-first sequencing."},
        {"role": "assistant", "content": "Noted."},
    ])

    assert provider._store.count_records() == 0
