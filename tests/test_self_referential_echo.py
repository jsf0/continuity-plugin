"""Regression tests for the self-referential echo penalty.

Memory-system fix/debug notes that embed the exact colloquial query they
document ("what oil should I use") used to win FTS on that query, beating the
genuine answer records. The penalty demotes such records when the query has no
memory_system facet; memory queries and non-memory records are unaffected.
"""

import pytest

from continuity.models import ContextRecord
from continuity.retrieval import ContinuityRetriever
from continuity.store import ContinuityStore


def _record(rid: str, kind: str, title: str, summary: str, details: str = "") -> ContextRecord:
    return ContextRecord(
        id=rid,
        kind=kind,
        title=title,
        summary=summary,
        details=details,
        embedding_text=f"kind: {kind}\ntitle: {title}\nsummary: {summary}\ndetails: {details}",
    )


@pytest.fixture()
def store(tmp_path):
    s = ContinuityStore(tmp_path / "continuity.db")
    s.migrate()
    s.upsert_record(
        _record(
            "r_wrx_oil",
            "user_preference",
            "Now owns 2021 Subaru WRX STI",
            "OEM engine oil spec: 5W-30 full synthetic, ILSAC GF-6/API SP Resource "
            "Conserving; capacity ~4.9 US qt with filter; interval 3,000-3,750 mi "
            "due to small sump plus turbo.",
            "Traded in the Raptor for a 2021 WRX STI (EJ257 2.5L turbo); oil "
            "changes use 5W-30, 5W-40 synthetic acceptable substitute.",
        )
    )
    s.upsert_record(
        _record(
            "r_continuity_fixnote",
            "environment_fact",
            "Continuity v0.1.4: FTS-anchor reranker bypass, graph reranker respect",
            "Fixes oil-eval records dying at the reranker for 'what oil should I use' "
            "queries; live-verified the oil record now selected on 'what oil should I "
            "use'. Graph neighbors respect the reranker; IDF-weighted text anchors.",
        )
    )
    s.upsert_record(
        _record(
            "r_plain_preference_mirror",
            "user_preference",
            "Always respond in English only",
            "Permanent rule, zero exceptions: always respond in English only "
            "regardless of the language the user writes in.",
        )
    )
    return s


def test_echo_quoting_note_demoted_below_real_answer(store):
    retriever = ContinuityRetriever(store)
    hits = retriever.search("what oil should I use", limit=3)

    ids = [h.record.id for h in hits]
    assert ids[0] == "r_wrx_oil"
    assert "r_continuity_fixnote" not in ids[:1]

    debug = retriever.debug_search("what oil should I use", limit=3)
    note = next(
        c for c in debug["selected"] + debug["rejected"] if c.record.id == "r_continuity_fixnote"
    )
    assert "self_referential_echo" in note.reasons
    assert note.penalties > 0


def test_memory_query_still_surfaces_fixnote(store):
    # Query about the memory system itself: no penalty, note stays rankable.
    retriever = ContinuityRetriever(store)
    hits = retriever.search("is the continuity reranker bypass working", limit=3)

    ids = [h.record.id for h in hits]
    assert "r_continuity_fixnote" in ids
    debug = retriever.debug_search("is the continuity reranker bypass working", limit=3)
    note = next(
        c for c in debug["selected"] + debug["rejected"] if c.record.id == "r_continuity_fixnote"
    )
    assert "self_referential_echo" not in note.reasons


def test_non_memory_record_quoting_query_not_penalized(store):
    # Preference mirrors legitimately quote stored instructions; the echo
    # penalty must not touch non-memory_system records.
    retriever = ContinuityRetriever(store)
    debug = retriever.debug_search("always respond in english only", limit=3)
    mirror = next(
        c
        for c in debug["selected"] + debug["rejected"]
        if c.record.id == "r_plain_preference_mirror"
    )
    assert "self_referential_echo" not in mirror.reasons


def test_penalty_disables_cleanly(store):
    from continuity.config import RetrievalGateConfig

    retriever = ContinuityRetriever(
        store, gate_config=RetrievalGateConfig(self_referential_echo_penalty=False)
    )
    debug = retriever.debug_search("what oil should I use", limit=3)
    for candidate in debug["selected"] + debug["rejected"]:
        assert "self_referential_echo" not in candidate.reasons


def test_short_queries_exempt(store):
    # Fewer than 3 tokens: no echo detection (too noisy).
    retriever = ContinuityRetriever(store)
    debug = retriever.debug_search("what oil", limit=3)
    for candidate in debug["selected"] + debug["rejected"]:
        assert "self_referential_echo" not in candidate.reasons
