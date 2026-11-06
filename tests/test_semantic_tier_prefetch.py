"""Regression tests for semantic-tier prefetch rendering and guidance."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from continuity.__init__ import (
    _continuity_system_guidance,
    _format_prefetch_context,
)
from continuity.models import ContextRecord
from continuity.retrieval import RetrievalHit


def _hit(rid: str, title: str, summary: str, role: str = "direct_seed") -> RetrievalHit:
    record = ContextRecord(
        id=rid,
        kind="user_preference",
        title=title,
        summary=summary,
        embedding_text=f"kind: user_preference\ntitle: {title}\nsummary: {summary}",
    )
    return RetrievalHit(record=record, score=5.0, reasons=("fts",), retrieval_role=role)


SEMANTIC_HEADING = (
    "Semantic matches (vector-only, no lexical anchor; may be irrelevant — judge for yourself):"
)


def test_semantic_offers_render_in_labeled_tier():
    hits = [
        _hit("r_anchor", "Anchored", "anchored summary"),
        _hit("r_sem", "Offered", "offered summary", role="semantic_candidate"),
    ]
    output, included = _format_prefetch_context(
        hits, max_chars=2000, include_sources=False, include_scores=False
    )
    assert SEMANTIC_HEADING in output
    assert [h.record.id for h in included] == ["r_anchor", "r_sem"]


def test_budget_reservation_protects_semantic_tier_from_long_anchored_record():
    # The 0.1.9 failure shape, inverted: a huge top-ranked anchored record
    # must not consume the budget the semantic offer needs.
    hits = [
        _hit("r_long", "Long", "x" * 1400),
        _hit("r_sem", "Offered", "y" * 300, role="semantic_candidate"),
    ]
    output, included = _format_prefetch_context(
        hits,
        max_chars=1000,
        include_sources=False,
        include_scores=False,
        semantic_budget_share=0.35,
    )
    ids = [h.record.id for h in included]
    assert ids[0] == "r_long"  # anchored first, truncated to its 65% cap
    assert "r_sem" in ids  # the offer still fits
    assert SEMANTIC_HEADING in output
    assert len(output) <= 1000


def test_no_reservation_when_no_semantic_offers():
    hits = [_hit("r_long", "Long", "x" * 1400)]
    output, included = _format_prefetch_context(
        hits,
        max_chars=1000,
        include_sources=False,
        include_scores=False,
        semantic_budget_share=0.35,
    )
    assert SEMANTIC_HEADING not in output
    assert [h.record.id for h in included] == ["r_long"]


def test_guidance_contains_no_false_absence_rule_and_tier_contract():
    guidance = _continuity_system_guidance()
    assert "NEVER state that something is not in memory" in guidance
    assert "Semantic matches" in guidance
    assert "MAY be irrelevant" in guidance
