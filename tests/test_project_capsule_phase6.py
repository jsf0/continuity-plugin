from __future__ import annotations

from pathlib import Path

from continuity.models import ContextRecord
from continuity.project import ProjectContext, build_project_capsule
from continuity.retrieval import ContinuityRetriever
from continuity.store import ContinuityStore


def record(
    record_id: str,
    kind: str,
    summary: str,
    *,
    scope_project: str = "guard-proxy",
) -> ContextRecord:
    return ContextRecord.new(
        id=record_id,
        kind=kind,
        title=summary[:48],
        summary=summary,
        scope_project=scope_project,
        tags=[kind],
        confidence=0.85,
        importance=0.8,
    )


def project() -> ProjectContext:
    return ProjectContext(
        project_id="git:https://github.com/example/guard-proxy.git",
        root=Path("/tmp/guard-proxy"),
        repo_root=Path("/tmp/guard-proxy"),
        repo_remote="https://github.com/example/guard-proxy.git",
        display_name="guard-proxy",
    )


def test_build_project_capsule_sections_and_dedupes() -> None:
    capsule = build_project_capsule(
        project(),
        [
            record("r1", "lesson_learned", "patch lint can falsely report Rust 2015 async errors."),
            record("r2", "lesson_learned", "patch lint can falsely report Rust 2015 async errors."),
            record("r3", "decision", "do not add auth layer to guard-proxy."),
            record("r4", "project_convention", "verify with cargo check and OpenBSD."),
        ],
    )

    assert capsule.id.startswith("capsule_")
    assert capsule.kind == "active_project_state"
    assert capsule.scope_project == "guard-proxy"
    assert capsule.scope_repo == "https://github.com/example/guard-proxy.git"
    assert "Known pitfalls:" in capsule.summary
    assert capsule.summary.count("patch lint can falsely report") == 1
    assert "User decisions:" in capsule.summary
    assert "Verification:" in capsule.summary


def test_project_capsule_is_preferred_for_project_over_individual_records(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    individual = record("r1", "lesson_learned", "patch lint can falsely report Rust 2015 async errors.")
    capsule = build_project_capsule(project(), [individual])
    store.upsert_record(individual)
    store.upsert_record(capsule)

    hits = ContinuityRetriever(store).search(
        "guard-proxy known pitfalls patch lint",
        scope_project="guard-proxy",
        limit=2,
    )

    assert hits[0].record.kind == "active_project_state"
    assert hits[0].record.id == capsule.id
