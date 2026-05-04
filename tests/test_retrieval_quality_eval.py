from __future__ import annotations

from pathlib import Path

from continuity.models import ContextRecord
from continuity.retrieval import ContinuityRetriever
from continuity.store import ContinuityStore


def _seeded_store(tmp_path: Path) -> ContinuityStore:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    records = [
        ContextRecord.new(
            id="raptor_boat_setup",
            kind="user_preference",
            title="Hermes user memory",
            summary=(
                "User has a 2018 Ford Raptor and likely has backyard space suitable "
                "for storing a small trailerable boat/catamaran."
            ),
            confidence=0.9,
            importance=0.75,
            trust_level="built_in_memory_mirror",
        ),
        ContextRecord.new(
            id="guard_proxy_old_root",
            kind="project_convention",
            title="Hermes global memory",
            summary=(
                "guard-proxy status 2026-05-02: HEAD cc78de9, tracked tree clean. "
                "Linux gates pass. OpenBSD gates pass. Production verdict strong/staging-ready."
            ),
            scope_project="root",
            confidence=0.9,
            importance=0.75,
            trust_level="built_in_memory_mirror",
        ),
        ContextRecord.new(
            id="framework_desktop",
            kind="environment_fact",
            title="Hermes global memory",
            summary=(
                "Framework Desktop plan: experiment with llama.cpp, ideally OpenBSD + Vulkan, "
                "and evaluate local models as GPT-5.5 replacements for Hermes-agent."
            ),
            confidence=0.9,
            importance=0.75,
            trust_level="built_in_memory_mirror",
        ),
        ContextRecord.new(
            id="continuity_noise_tuning",
            kind="lesson_learned",
            title="Association graph noise tuning implemented",
            summary=(
                "Continuity memory retrieval noise tuning: meta queries about association graph, "
                "memory records, and retrieval should suppress generic mirror memories unless "
                "they have continuity-domain anchors."
            ),
            scope_project="hermes-continuity-memory",
            tags=["continuity", "retrieval", "association-graph", "noise"],
            entities=["continuity", "association graph", "retrieval"],
            confidence=0.9,
            importance=0.8,
        ),
    ]
    for record in records:
        store.upsert_record(record)
    return store


def _ids_for(query: str, tmp_path: Path, *, scope_project: str | None = "root") -> list[str]:
    retriever = ContinuityRetriever(_seeded_store(tmp_path))
    return [hit.record.id for hit in retriever.search(query, scope_project=scope_project, limit=3)]


def test_boat_towing_query_retrieves_raptor_not_guard_proxy(tmp_path: Path) -> None:
    ids = _ids_for("what kinds of boats can i tow with my setup?", tmp_path)

    assert "raptor_boat_setup" in ids[:3]
    assert "guard_proxy_old_root" not in ids[:3]


def test_framework_query_retrieves_framework_not_raptor(tmp_path: Path) -> None:
    ids = _ids_for("what should I do first when my Framework Desktop arrives?", tmp_path)

    assert "framework_desktop" in ids[:3]
    assert "raptor_boat_setup" not in ids[:3]


def test_guard_proxy_query_retrieves_guard_proxy_not_raptor(tmp_path: Path) -> None:
    ids = _ids_for("what is the current guard-proxy status?", tmp_path)

    assert "guard_proxy_old_root" in ids[:3]
    assert "raptor_boat_setup" not in ids[:3]


def test_memory_meta_query_suppresses_generic_mirror_records(tmp_path: Path) -> None:
    ids = _ids_for(
        "how do we fix the remaining noise issue in memory records and association links?",
        tmp_path,
        scope_project="hermes-continuity-memory",
    )

    assert ids[0] == "continuity_noise_tuning"
    assert "framework_desktop" not in ids[:3]
    assert "raptor_boat_setup" not in ids[:3]
