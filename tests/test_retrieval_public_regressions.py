from __future__ import annotations

from pathlib import Path

import pytest

from continuity.models import ContextRecord
from continuity.reranking import RerankHit
from continuity.retrieval import ContinuityRetriever
from continuity.store import ContinuityStore


class RejectingReranker:
    def is_available(self) -> bool:
        return True

    def rerank(self, query: str, records: list[ContextRecord]) -> list[RerankHit]:
        return [RerankHit(record_id=record.id, score=0.01) for record in records]


def _record(
    record_id: str,
    title: str,
    summary: str,
    *,
    tags: list[str] | None = None,
    entities: list[str] | None = None,
    kind: str = "user_preference",
    trust_level: str = "explicit_user",
) -> ContextRecord:
    return ContextRecord.new(
        id=record_id,
        kind=kind,
        title=title,
        summary=summary,
        tags=tags or [],
        entities=entities or [],
        confidence=0.9,
        importance=0.8,
        trust_level=trust_level,
    )


def _store(tmp_path: Path) -> ContinuityStore:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    records = [
        _record(
            "van_context",
            "Blue Ridge Utility Van towing setup",
            "User has access to a Blue Ridge Utility Van for towing and hauling weekend gear.",
            tags=["vehicle", "towing", "trailer", "utility van"],
            entities=["Blue Ridge Utility Van"],
        ),
        _record(
            "camper_context",
            "Folding camper shopping context",
            "User is comparing lightweight folding campers that are easy to store and pull on small trips.",
            tags=["camper", "folding camper", "trailer", "storage", "towing"],
            entities=["Blue Ridge Utility Van"],
        ),
        _record(
            "generic_towing_retrieval_note",
            "Continuity retrieval should stay general-purpose",
            "User wants continuity-memory improvements to be general-purpose, not hardcoded for specific towing examples.",
            tags=["towing", "retrieval"],
            entities=[],
        ),
        _record(
            "work_style_preference",
            "Preferred code-change working style",
            "User prefers methodical, thorough code changes with reasoning before edits, tests passing, and docs updated.",
            tags=["preference", "work_style", "code changes", "testing", "docs"],
            entities=["code-change workflow"],
        ),
        _record(
            "workstation_context",
            "Atlas Workstation local inference setup",
            "User owns an Atlas Workstation used for local model experiments and GPU testing.",
            tags=["hardware", "workstation", "local model"],
            entities=["Atlas Workstation"],
        ),
        _record(
            "software_framework_context",
            "Web application framework decision",
            "Project needs a web application framework for API handlers, routing, and middleware.",
            tags=["software", "framework", "api", "web", "routing"],
            entities=["web application framework"],
            kind="project_convention",
        ),
        _record(
            "memory_context",
            "Memory provider retrieval graph",
            "The memory provider uses retrieval, reranking, and association graph debugging to explain recalled records.",
            tags=["memory", "retrieval", "association graph", "reranking"],
            entities=["memory provider", "association graph"],
            kind="lesson_learned",
        ),
    ]
    for record in records:
        store.upsert_record(record)
    return store


RETRIEVAL_REGRESSION_CASES = [
    pytest.param(
        "how much camper can I pull?",
        {"camper_context", "van_context"},
        {"generic_towing_retrieval_note", "memory_context", "software_framework_context"},
        False,
        id="anchored-personal-towing-positive-with-noise-forbidden",
    ),
    pytest.param(
        "how do I prefer you handle code changes?",
        {"work_style_preference"},
        {"generic_towing_retrieval_note", "memory_context", "software_framework_context"},
        False,
        id="personal-work-style-preference",
    ),
    pytest.param(
        "what framework should this API use?",
        {"software_framework_context"},
        {"workstation_context", "memory_context", "generic_towing_retrieval_note"},
        False,
        id="software-framework-not-hardware-or-memory-meta",
    ),
    pytest.param(
        "what GPU does my workstation have?",
        {"workstation_context"},
        {"software_framework_context", "memory_context", "van_context"},
        False,
        id="personal-hardware-not-software-framework",
    ),
    pytest.param(
        "why did the association graph retrieve that memory record?",
        {"memory_context"},
        {"van_context", "camper_context", "workstation_context"},
        False,
        id="memory-meta-query-positive",
    ),
    pytest.param(
        "how about now?",
        set(),
        {"van_context", "camper_context", "memory_context", "work_style_preference"},
        True,
        id="low-information-no-context",
    ),
]


@pytest.mark.parametrize(
    ("query", "expected_ids", "forbidden_ids", "expect_no_context"),
    RETRIEVAL_REGRESSION_CASES,
)
def test_retrieval_regression_suite_tracks_recall_and_precision(
    tmp_path: Path,
    query: str,
    expected_ids: set[str],
    forbidden_ids: set[str],
    expect_no_context: bool,
) -> None:
    hits = ContinuityRetriever(_store(tmp_path), association_enabled=True).search(query, limit=5)
    hit_ids = {hit.record.id for hit in hits}

    if expect_no_context:
        assert hit_ids == set()
    else:
        assert expected_ids <= hit_ids
    assert hit_ids.isdisjoint(forbidden_ids)


def test_dynamic_expansion_recovers_related_towing_context_without_domain_aliases(
    tmp_path: Path,
) -> None:
    debug = ContinuityRetriever(_store(tmp_path), association_enabled=True).debug_search(
        "how much camper can I pull?", limit=5
    )

    selected_ids = [candidate.record.id for candidate in debug["selected"]]
    assert "camper_context" in selected_ids
    assert "van_context" in selected_ids
    expansion_terms = {term["term"] for term in debug.get("dynamic_expansion", [])}
    assert {"towing", "trailer"} & expansion_terms


def test_personal_context_with_strong_metadata_survives_cold_reranker(
    tmp_path: Path,
) -> None:
    debug = ContinuityRetriever(
        _store(tmp_path),
        reranker_backend=RejectingReranker(),
        reranker_min_score=0.15,
        association_enabled=True,
    ).debug_search("how much camper can I pull with my setup?", limit=5)

    selected_by_id = {candidate.record.id: candidate for candidate in debug["selected"]}
    assert selected_by_id["camper_context"].retrieval_role == "direct_seed"
    assert "strong_personal_anchor" in selected_by_id["camper_context"].reasons
    assert selected_by_id["van_context"].retrieval_role == "direct_seed"
    assert "strong_personal_anchor" in selected_by_id["van_context"].reasons
    assert "generic_towing_retrieval_note" not in selected_by_id


def test_ambiguous_framework_query_does_not_retrieve_unrelated_hardware(
    tmp_path: Path,
) -> None:
    hits = ContinuityRetriever(_store(tmp_path), association_enabled=True).search(
        "what framework should this API use?", limit=5
    )

    hit_ids = [hit.record.id for hit in hits]
    assert "software_framework_context" in hit_ids
    assert "workstation_context" not in hit_ids


def test_low_information_query_injects_no_context(tmp_path: Path) -> None:
    hits = ContinuityRetriever(_store(tmp_path), association_enabled=True).search(
        "how about now?", limit=5
    )

    assert hits == []


def test_memory_meta_query_retrieves_memory_system_record(tmp_path: Path) -> None:
    hits = ContinuityRetriever(_store(tmp_path), association_enabled=True).search(
        "why did the association graph retrieve that memory record?", limit=5
    )

    assert [hit.record.id for hit in hits][:1] == ["memory_context"]
