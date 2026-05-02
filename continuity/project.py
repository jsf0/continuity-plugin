"""Project identity detection for scoped continuity retrieval."""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from continuity.models import ContextRecord, SourceRef


@dataclass(frozen=True)
class ProjectContext:
    """Detected project identity for the current turn/session."""

    project_id: str
    root: Path
    display_name: str
    repo_root: Path | None = None
    repo_remote: str | None = None


def build_project_capsule(project: ProjectContext, records: list[ContextRecord]) -> ContextRecord:
    """Build a compact active-project-state capsule from project-scoped records."""
    scoped = [
        record
        for record in records
        if record.kind != "active_project_state"
        and (
            record.scope_project in {None, project.display_name}
            or record.scope_repo == project.repo_remote
        )
    ]
    sections = [f"Project: {project.display_name}."]
    sections.extend(_section("Known pitfalls", _summaries_for(scoped, {"lesson_learned"})))
    sections.extend(_section("User decisions", _summaries_for(scoped, {"decision"})))
    sections.extend(_section("Verification", _summaries_for(scoped, {"project_convention"})))
    sections.extend(_section("User preferences", _summaries_for(scoped, {"user_preference"})))
    if len(sections) == 1:
        sections.append("No durable project facts recorded yet.")
    sources = [SourceRef(type="memory", id=record.id, label=record.kind) for record in scoped[:20]]
    return ContextRecord.new(
        id=f"capsule_{_stable_hash(project.project_id)}",
        kind="active_project_state",
        title=f"Project capsule: {project.display_name}",
        summary="\n".join(sections),
        scope_project=project.display_name,
        scope_repo=project.repo_remote,
        tags=["project_capsule", "active_project_state", project.display_name],
        entities=[project.project_id, project.repo_remote or project.display_name],
        sources=sources,
        confidence=0.85,
        importance=0.95,
        trust_level="agent_observed",
    )


def _section(title: str, items: list[str]) -> list[str]:
    if not items:
        return []
    return [f"{title}:", *[f"- {item}" for item in items[:8]]]


def _summaries_for(records: list[ContextRecord], kinds: set[str]) -> list[str]:
    seen: set[str] = set()
    summaries: list[str] = []
    for record in records:
        if record.kind not in kinds:
            continue
        normalized = " ".join(record.summary.lower().split())
        if normalized in seen:
            continue
        seen.add(normalized)
        summaries.append(record.summary)
    return summaries


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
