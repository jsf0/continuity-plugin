"""Project identity detection for scoped continuity retrieval."""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectContext:
    """Detected project identity for the current turn/session."""

    project_id: str
    root: Path
    display_name: str
    repo_root: Path | None = None
    repo_remote: str | None = None


def detect_project(cwd: Path | str | None = None) -> ProjectContext:
    """Detect project identity from TERMINAL_CWD, cwd, and git metadata."""
    root = _effective_cwd(cwd)
    repo_root = _git_root(root)
    repo_remote = _git_remote(repo_root) if repo_root else None

    if repo_remote:
        return ProjectContext(
            project_id=f"git:{repo_remote}",
            root=root,
            repo_root=repo_root,
            repo_remote=repo_remote,
            display_name=_remote_display_name(repo_remote),
        )
    if repo_root:
        return ProjectContext(
            project_id=f"git-path:{_stable_hash(str(repo_root))}",
            root=root,
            repo_root=repo_root,
            repo_remote=None,
            display_name=repo_root.name,
        )
    return ProjectContext(
        project_id=f"path:{_stable_hash(str(root))}",
        root=root,
        display_name=root.name or str(root),
    )


def _effective_cwd(cwd: Path | str | None) -> Path:
    if cwd is not None:
        return Path(cwd).expanduser().resolve()
    env_cwd = os.environ.get("TERMINAL_CWD")
    if env_cwd:
        return Path(env_cwd).expanduser().resolve()
    return Path.cwd().resolve()


def _git_root(path: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    text = result.stdout.strip()
    return Path(text).resolve() if text else None


def _git_remote(repo_root: Path | None) -> str | None:
    if repo_root is None:
        return None
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    text = result.stdout.strip()
    return text or None


def _remote_display_name(remote: str) -> str:
    name = remote.rstrip("/").removesuffix(".git").split("/")[-1]
    if ":" in name:
        name = name.split(":")[-1]
    return name or remote


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
