"""Dynamic query expansion derived from stored memory records."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .models import ContextRecord
from .store import ContinuityStore
from .vocabulary import CorpusTermStats, normalize_phrase, tokenize_text


@dataclass(frozen=True)
class ExpansionTerm:
    term: str
    source: str
    source_record_ids: tuple[str, ...]
    score: float
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "term": self.term,
            "source": self.source,
            "source_record_ids": list(self.source_record_ids),
            "score": self.score,
            "reason": self.reason,
        }


def propose_expansion_terms(
    query_tokens: set[str],
    candidates: Iterable[object],
    store: ContinuityStore,
    stats: CorpusTermStats,
    *,
    max_terms: int = 8,
    min_candidate_score: float = 0.35,
) -> list[ExpansionTerm]:
    """Propose bounded expansion terms from anchored candidate metadata.

    Candidates are expected to be CandidateScore-like objects with record and
    score attributes.  This loose coupling avoids importing retrieval internals.
    """
    del store  # reserved for graph-neighbor expansion; keeps API stable.
    proposed: dict[str, ExpansionTerm] = {}
    normalized_query = {
        normalize_phrase(token) for token in query_tokens if normalize_phrase(token)
    }
    if not normalized_query or (
        len(normalized_query) <= 1 and next(iter(normalized_query), "") in {"now", "ok"}
    ):
        return []
    strong_query_tokens = normalized_query - GENERIC_EXPANSION_ANCHOR_TOKENS
    if not strong_query_tokens:
        return []

    for candidate in candidates:
        record = getattr(candidate, "record", None)
        if record is None or not _candidate_has_anchor(candidate):
            continue
        candidate_score = float(getattr(candidate, "base_relevance", 0.0))
        if candidate_score < min_candidate_score:
            continue
        _collect_record_terms(
            proposed,
            record,
            strong_query_tokens,
            stats,
            source_record_id=record.id,
        )

    return sorted(proposed.values(), key=lambda term: (-term.score, term.term))[:max_terms]


# Generic verbs/filler that must not, by themselves, anchor expansion-term
# harvesting.  Observed: "what phone do I use" harvested "sync api",
# "page wait for selector" etc. from a browser-skill record whose only link
# to the query was the token "use".
GENERIC_EXPANSION_ANCHOR_TOKENS = frozenset(
    {
        "use",
        "uses",
        "using",
        "used",
        "handle",
        "make",
        "makes",
        "get",
        "gets",
        "need",
        "needs",
        "want",
        "wants",
        "like",
        "likes",
        "know",
        "knows",
        "think",
        "help",
        "should",
        "best",
        "good",
    }
)


def _candidate_has_anchor(candidate: object) -> bool:
    # Dynamic expansion should come from structured metadata evidence, not mere
    # body-text/FTS coincidences. Text-only expansion caused semantic drift on
    # broad queries such as "what API framework should we use?" by harvesting
    # unrelated entities from records that merely quoted similar words.
    return any(float(getattr(candidate, attr, 0.0)) > 0 for attr in ("tag_score", "entity_score"))


def _collect_record_terms(
    proposed: dict[str, ExpansionTerm],
    record: ContextRecord,
    query_tokens: set[str],
    stats: CorpusTermStats,
    *,
    source_record_id: str,
) -> None:
    for source, values, base in (
        ("entity", record.entities, 1.1),
        ("tag", record.tags, 1.0),
    ):
        for value in values:
            normalized = normalize_phrase(value)
            if (
                not normalized
                or normalized in query_tokens
                or stats.is_generic(normalized, max_document_fraction=0.6)
            ):
                continue
            # Prefer metadata whose record also contains at least one query token.
            record_terms = tokenize_text(
                " ".join(
                    [
                        record.title,
                        record.summary,
                        record.details or "",
                        *record.tags,
                        *record.entities,
                    ]
                )
            )
            if not (record_terms & query_tokens):
                continue
            score = base * stats.idf(normalized)
            existing = proposed.get(normalized)
            if existing is None or score > existing.score:
                proposed[normalized] = ExpansionTerm(
                    term=normalized,
                    source=source,
                    source_record_ids=(source_record_id,),
                    score=score,
                    reason=f"high_idf_{source}_from_anchored_candidate",
                )
