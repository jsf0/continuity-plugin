"""Regression tests for prefetch budget truncation (record length must not
subvert score order).

Live failure (Nov 5 2026, autocross session): the top-ranked hit had a very
long summary, consumed most of the 1800-char injection budget, and the #2 hit
(the WRX ownership record) did not fit — so it was silently SKIPPED while a
smaller, lower-scoring #3 record was injected. The answer to the user's
question was ranked #2 and never shown.

_fix_hit now truncates the summary to fit the remaining budget instead of
dropping the record.
"""

from continuity.__init__ import _format_prefetch_context
from continuity.models import ContextRecord
from continuity.retrieval import RetrievalHit


def _hit(rid: str, title: str, summary: str, score: float) -> RetrievalHit:
    record = ContextRecord(
        id=rid,
        kind="environment_fact",
        title=title,
        summary=summary,
        embedding_text=f"kind: environment_fact\ntitle: {title}\nsummary: {summary}",
    )
    return RetrievalHit(record=record, score=score, reasons=("fts",))


def test_long_first_hit_must_not_squeeze_out_higher_ranked_second(tmp_path=None):
    hits = [
        _hit("r_long_top", "Long top record", "x" * 1400, 13.6),
        _hit("r_second", "Second-ranked record", "y" * 600, 8.4),
        _hit("r_small_third", "Small third record", "z" * 200, 5.8),
    ]

    output, included = _format_prefetch_context(
        hits, max_chars=1800, include_sources=False, include_scores=False
    )

    included_ids = [hit.record.id for hit in included]
    # Old behavior: r_second skipped entirely (didn't fit), r_small_third
    # included instead. New behavior: r_second included, truncated.
    assert "r_second" in included_ids
    assert len(output) <= 1800
    # Truncation is visible.
    assert output.count("...") >= 1


def test_hits_fit_untouched_when_budget_generous():
    hits = [
        _hit("r_a", "Record A", "short summary a", 5.0),
        _hit("r_b", "Record B", "short summary b", 4.0),
    ]
    output, included = _format_prefetch_context(
        hits, max_chars=2000, include_sources=False, include_scores=False
    )
    assert [h.record.id for h in included] == ["r_a", "r_b"]
    assert "short summary a" in output
    assert "..." not in output


def test_hit_dropped_only_when_budget_too_small_for_fragment():
    hits = [
        _hit("r_huge", "Huge", "h" * 5000, 9.0),
        _hit("r_next", "Next", "n" * 5000, 8.0),
    ]
    output, included = _format_prefetch_context(
        hits, max_chars=300, include_sources=False, include_scores=False
    )
    # First hit gets truncated in; second cannot render a >=100-char fragment.
    assert [h.record.id for h in included] == ["r_huge"]
    assert len(output) <= 300
