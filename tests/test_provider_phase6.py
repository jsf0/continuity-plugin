from __future__ import annotations

from pathlib import Path

from continuity import ContinuityProvider


def test_on_session_end_updates_project_capsule(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "guard-proxy"
    project_dir.mkdir()
    monkeypatch.setenv("TERMINAL_CWD", str(project_dir))
    provider = ContinuityProvider()
    provider.initialize(
        session_id="capsule-session",
        hermes_home=str(tmp_path / "hermes"),
        continuity_config={"consolidate_min_turns": 1},
    )
    assert provider._store is not None

    provider.on_session_end(
        [
            {"role": "user", "content": "Remember: I prefer foundation-first sequencing."},
            {"role": "assistant", "content": "Lesson learned: patch lint can falsely report Rust 2015 async errors."},
            {"role": "assistant", "content": "Decision: do not add auth layer to guard-proxy."},
        ]
    )

    records = provider._store.list_records()
    capsules = [record for record in records if record.kind == "active_project_state"]
    assert len(capsules) == 1
    capsule = capsules[0]
    assert capsule.scope_project == "guard-proxy"
    assert "patch lint can falsely report" in capsule.summary
    assert "do not add auth layer" in capsule.summary

    # Running consolidation again should update the same capsule, not create another one.
    provider.on_session_end(
        [
            {"role": "user", "content": "Remember: I prefer foundation-first sequencing."},
            {"role": "assistant", "content": "Lesson learned: patch lint can falsely report Rust 2015 async errors."},
        ]
    )
    capsules = [record for record in provider._store.list_records() if record.kind == "active_project_state"]
    assert len(capsules) == 1
