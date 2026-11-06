"""Regression tests for the semantic-candidate tier and expansion-anchor hygiene.

Observed live failures that motivated these (Nov 2026, v0.2.0 tier):
- "What car do I drive?" and "what maintenance do I need for my car" selected
  nothing: the personal vehicle record was rejected by the weak-vector-only
  gate because the query shared no lexical token with it ("car"/"drive" never
  appear in the record text). The semantic-candidate tier now offers the top
  vector-only match above a raw-cosine floor to the consuming model, with no
  query-pattern rules (the verb-based and possessive rescues it replaces were
  whack-a-mole).
- "how do we handle firmware updates for dell servers" rejected the
  project's own firmware-controller record because "handle" tagged the
  query as a personal-preference query, making the record facet-incompatible.
- "what phone do I use" harvested junk expansion terms ("sync api",
  "page wait for selector") from a browser-skill record whose only link to
  the query was the generic verb "use".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from continuity.dynamic_expansion import propose_expansion_terms
from continuity.embeddings import VectorHit
from continuity.models import ContextRecord
from continuity.retrieval import (
    ContinuityRetriever,
    _is_preference_query,
)
from continuity.store import ContinuityStore


class StubVectorBackend:
    """Vector backend returning fixed hits, for deterministic tests."""

    def __init__(self, hits: list[VectorHit]) -> None:
        self._hits = hits

    def is_available(self) -> bool:
        return True

    def upsert(self, record_id: str, text: str) -> None:
        return None

    def delete(self, record_id: str) -> None:
        return None

    def search(self, query: str, limit: int) -> list[VectorHit]:
        return self._hits[:limit]


def _store_with(tmp_path: Path, records: list[ContextRecord]) -> ContinuityStore:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    for record in records:
        store.upsert_record(record)
    return store


def _car_record() -> ContextRecord:
    # Deliberately contains neither "car" nor "drive": the answer is only
    # reachable through vector similarity on an ownership-style query.
    return ContextRecord.from_dict(
        {
            "id": "r_wrx",
            "kind": "user_preference",
            "title": "Now owns 2021 Subaru WRX STI",
            "summary": "Traded the Raptor for a 2021 Subaru WRX STI (EJ257 turbo).",
            "tags": ["vehicle"],
            "entities": ["Subaru WRX STI", "EJ257"],
            "confidence": 0.9,
            "importance": 0.8,
        }
    )


def test_ownership_query_offers_semantic_candidate(tmp_path: Path) -> None:
    store = _store_with(tmp_path, [_car_record()])
    # vector_score = 0.7 * 3.0 = 2.1: below the strict 2.75 vector-only gate,
    # but raw cosine 0.7 >= the 0.46 tier floor -> offered as semantic candidate.
    retriever = ContinuityRetriever(
        store, vector_backend=StubVectorBackend([VectorHit("r_wrx", 0.7)])
    )

    hits = retriever.search("What car do I drive?", limit=3)

    assert [hit.record.id for hit in hits] == ["r_wrx"]
    assert "semantic_candidate" in hits[0].reasons
    assert hits[0].retrieval_role == "semantic_candidate"


def test_ownership_rescue_requires_personal_kind(tmp_path: Path) -> None:
    project_record = ContextRecord.from_dict(
        {
            "id": "r_proj",
            "kind": "project_convention",
            "scope_project": "guard-proxy",
            "title": "Deploy workflow uses racadm and SUM",
            "summary": "Firmware tooling conventions for the fleet.",
            "tags": ["firmware"],
            "entities": ["racadm", "SUM"],
            "confidence": 0.9,
            "importance": 0.8,
        }
    )
    store = _store_with(tmp_path, [project_record])
    retriever = ContinuityRetriever(
        store, vector_backend=StubVectorBackend([VectorHit("r_proj", 0.7)])
    )

    hits = retriever.search("What car do I drive?", limit=3)

    assert not any("ownership_query_vector_rescue" in hit.reasons for hit in hits)


def test_tier_floor_still_rejects_weak_vectors(tmp_path: Path) -> None:
    store = _store_with(tmp_path, [_car_record()])
    # vector_score = 0.3 * 3.0 = 0.9: raw cosine 0.3 < the 0.46 tier floor.
    retriever = ContinuityRetriever(
        store, vector_backend=StubVectorBackend([VectorHit("r_wrx", 0.3)])
    )

    hits = retriever.search("What car do I drive?", limit=3)

    assert not hits


def test_handle_is_not_a_preference_token() -> None:
    assert not _is_preference_query({"handle"}, personal_query=True)
    assert _is_preference_query({"prefer"}, personal_query=True)


def test_procedural_handle_query_reaches_project_records(tmp_path: Path) -> None:
    record = ContextRecord.from_dict(
        {
            "id": "r_fwctl",
            "kind": "active_project_state",
            "scope_project": "firmware-omni-controller",
            "title": "Firmware update controller design v1",
            "summary": "Multi-vendor firmware controller: racadm, SUM, Redfish drivers.",
            "tags": ["firmware", "dell"],
            "entities": ["racadm", "Redfish"],
            "confidence": 0.9,
            "importance": 0.9,
        }
    )
    store = _store_with(tmp_path, [record])
    retriever = ContinuityRetriever(store)

    hits = retriever.search("how do we handle firmware updates for dell servers", limit=3)

    assert hits and hits[0].record.id == "r_fwctl"


@dataclass
class _FakeCandidate:
    record: ContextRecord
    tag_score: float = 1.0
    entity_score: float = 0.0
    base_relevance: float = 1.0
    reasons: list[str] = field(default_factory=list)


class _Stats:
    def is_generic(self, term: str, max_document_fraction: float = 0.6) -> bool:
        return False

    def idf(self, term: str) -> float:
        return 2.0


def test_expansion_ignores_candidates_anchored_only_on_generic_verbs(tmp_path: Path) -> None:
    # A browser-skill record whose only overlap with the query is "use".
    browser_record = ContextRecord.from_dict(
        {
            "id": "r_browser",
            "kind": "environment_fact",
            "title": "Headless browser skill workflow",
            "summary": "Use page.wait_for_selector and the sync API.",
            "tags": ["browser"],
            "entities": ["sync api", "page wait for selector"],
            "confidence": 0.9,
            "importance": 0.8,
        }
    )
    terms = propose_expansion_terms(
        {"use", "phone"},
        [_FakeCandidate(browser_record)],
        _store_with(tmp_path, []),
        _Stats(),
    )
    assert terms == []


def test_expansion_still_harvests_from_strongly_anchored_candidates(tmp_path: Path) -> None:
    firmware_record = ContextRecord.from_dict(
        {
            "id": "r_fw",
            "kind": "active_project_state",
            "title": "Dell firmware update driver",
            "summary": "racadm difference reports for dell BIOS and iDRAC firmware.",
            "tags": ["firmware"],
            "entities": ["racadm", "iDRAC"],
            "confidence": 0.9,
            "importance": 0.9,
        }
    )

    terms = propose_expansion_terms(
        {"dell", "firmware"},
        [_FakeCandidate(firmware_record)],
        _store_with(tmp_path, []),
        _Stats(),
    )
    harvested = {term.term for term in terms}
    assert harvested  # positive control: real anchors still expand
    assert "racadm" in harvested


def test_possessive_query_offers_semantic_candidate(tmp_path: Path) -> None:
    # Live failure (Nov 5 2026 autocross session): "what maintenance do I
    # need for my car" has NO ownership verb, no possession trigger needed
    # under the tier — the vector-only match above the floor is offered for
    # ANY query shape. That is the whole point: no pattern rules.
    store = _store_with(tmp_path, [_car_record()])
    retriever = ContinuityRetriever(
        store, vector_backend=StubVectorBackend([VectorHit("r_wrx", 0.7)])
    )

    hits = retriever.search("what maintenance do I need for my car", limit=3)

    assert [hit.record.id for hit in hits] == ["r_wrx"]
    assert "semantic_candidate" in hits[0].reasons


def test_possessive_rescue_still_requires_personal_kind_and_floor(
    tmp_path: Path,
) -> None:
    store = _store_with(tmp_path, [_car_record()])
    # Below the half-threshold floor: possession alone must not admit
    # semantically weak hits.
    retriever = ContinuityRetriever(
        store, vector_backend=StubVectorBackend([VectorHit("r_wrx", 0.3)])
    )
    hits = retriever.search("what maintenance do I need for my car", limit=3)
    assert not any("ownership_query_vector_rescue" in hit.reasons for hit in hits)


def test_non_possessive_query_also_gets_the_offer(tmp_path: Path) -> None:
    # Pattern-free by design: even without "my"/"drive"/"own", a strong
    # vector-only match is offered. The consuming model disposes.
    store = _store_with(tmp_path, [_car_record()])
    retriever = ContinuityRetriever(
        store, vector_backend=StubVectorBackend([VectorHit("r_wrx", 0.7)])
    )
    hits = retriever.search("what should I do about upgrades", limit=3)
    assert hits and hits[0].record.id == "r_wrx"
    assert "semantic_candidate" in hits[0].reasons
