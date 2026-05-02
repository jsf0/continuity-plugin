from __future__ import annotations

from pathlib import Path

from continuity.store import ContinuityStore


def test_add_session_observation_redacts_and_truncates_content(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()

    store.add_session_observation(
        session_id="s1",
        turn_index=1,
        user_content="token sk-1234567890abcdef and " + "u" * 500,
        assistant_content="assistant says " + "a" * 500,
        max_chars=80,
    )

    observations = store.list_unconsolidated_observations("s1")
    assert len(observations) == 1
    observation = observations[0]
    assert "sk-1234567890abcdef" not in observation["user_content"]
    assert "[REDACTED_SECRET]" in observation["user_content"]
    assert len(observation["user_content"]) <= 80
    assert len(observation["assistant_content"]) <= 80


def test_mark_session_observations_consolidated(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    store.add_session_observation(
        session_id="s1",
        turn_index=1,
        user_content="remember this lesson",
        assistant_content="saved",
        max_chars=200,
    )

    store.mark_session_observations_consolidated("s1")

    assert store.list_unconsolidated_observations("s1") == []
