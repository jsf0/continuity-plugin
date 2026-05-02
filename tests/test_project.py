from __future__ import annotations

import subprocess
from pathlib import Path

from continuity.project import detect_project


def test_detect_project_uses_terminal_cwd_path_fallback(tmp_path: Path, monkeypatch) -> None:
    workdir = tmp_path / "plain-project"
    workdir.mkdir()
    monkeypatch.setenv("TERMINAL_CWD", str(workdir))

    project = detect_project()

    assert project.root == workdir
    assert project.repo_root is None
    assert project.repo_remote is None
    assert project.display_name == "plain-project"
    assert project.project_id.startswith("path:")


def test_detect_project_uses_git_remote_identity(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example/demo.git"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    nested = repo / "src" / "pkg"
    nested.mkdir(parents=True)
    monkeypatch.setenv("TERMINAL_CWD", str(nested))

    project = detect_project()

    assert project.root == nested
    assert project.repo_root == repo
    assert project.repo_remote == "https://github.com/example/demo.git"
    assert project.project_id == "git:https://github.com/example/demo.git"
    assert project.display_name == "demo"
