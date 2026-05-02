"""Retrieval and scoring for continuity memory records."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .embeddings import VectorBackend
from .models import ContextRecord, SkillLink
from .store import ContinuityStore

SCOPE_BONUS = 2.0
TAG_BONUS = 1.5
ENTITY_BONUS = 1.75
CONFIDENCE_WEIGHT = 0.75
IMPORTANCE_WEIGHT = 0.75
FTS_WEIGHT = 1.0
VECTOR_WEIGHT = 3.0
CAPSULE_SCOPE_BONUS = 4.0
TRUST_PENALTIES = {
    "remote_untrusted": 1.0,
}

ALIASES = {
    "subagent": {"delegate_task", "delegation"},
    "subagents": {"delegate_task", "delegation"},
    "timed": {"timeout"},
    "timeout": {"timeout"},
    "timeouts": {"timeout"},
    "cleanup": {"foundation", "foundation-first"},
}

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "again",
        "are",
        "doing",
        "for",
        "how",
        "i",
        "in",
        "is",
        "it",
        "of",
        "out",
        "the",
        "thing",
        "to",
        "was",
        "we",
        "what",
        "without",
    }
)


@dataclass(frozen=True)
class RetrievalHit:
    """Ranked retrieval result."""

    record: ContextRecord
    score: float
    reasons: tuple[str, ...]
    skill_links: tuple[SkillLink, ...] = ()


class ContinuityRetriever:
    """Hybrid FTS + metadata + optional vector retriever for continuity records."""

    def __init__(
        self, store: ContinuityStore, *, vector_backend: VectorBackend | None = None
    ) -> None:
        self.store = store
        self.vector_backend = vector_backend

    def search(
        self,
        query: str,
        *,
        scope_project: object = None,
        limit: int = 5,
    ) -> list[RetrievalHit]:
        tokens = _query_tokens(query)
        expanded_tokens = _expand_tokens(tokens)
        candidates: dict[str, tuple[ContextRecord, float, list[str]]] = {}

        for hit in self.store.fts_search(" ".join(expanded_tokens), limit=max(limit * 4, 20)):
            base = max(0.0, 1.0 / (1.0 + abs(hit.rank))) * FTS_WEIGHT
            candidates[hit.record.id] = (hit.record, base, ["fts"])

        if self.vector_backend and self.vector_backend.is_available():
            for vector_hit in self.vector_backend.search(query, limit=max(limit * 4, 20)):
                record = self.store.get_record(vector_hit.record_id)
                if record is None:
                    self.vector_backend.delete(vector_hit.record_id)
                    continue
                vector_score = max(0.0, vector_hit.score) * VECTOR_WEIGHT
                existing = candidates.get(record.id)
                if existing:
                    _, current_score, reasons = existing
                    candidates[record.id] = (
                        record,
                        current_score + vector_score,
                        [*reasons, "vector"],
                    )
                elif vector_score > 0:
                    candidates[record.id] = (record, vector_score, ["vector"])

        for record in self.store.list_records():
            metadata_score, metadata_reasons = _metadata_score(
                record,
                expanded_tokens,
                scope_project=str(scope_project) if scope_project else None,
            )
            if metadata_score <= 0 and record.id not in candidates:
                continue
            existing = candidates.get(record.id)
            if existing:
                _, current_score, reasons = existing
                candidates[record.id] = (
                    record,
                    current_score + metadata_score,
                    reasons + metadata_reasons,
                )
            else:
                candidates[record.id] = (record, metadata_score, metadata_reasons)

        hits = [
            RetrievalHit(
                record=record,
                score=score,
                reasons=tuple(reasons),
                skill_links=tuple(self.store.list_skill_links(record.id)),
            )
            for record, score, reasons in candidates.values()
            if score > 0
        ]
        hits.sort(key=lambda hit: (-hit.score, hit.record.id))
        return hits[:limit]


def _metadata_score(
    record: ContextRecord,
    tokens: set[str],
    *,
    scope_project: str | None,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    record_tags = {_normalize_token(tag) for tag in record.tags}
    record_entities = {_normalize_token(entity) for entity in record.entities}
    record_text_tokens = _query_tokens(f"{record.title} {record.summary} {record.details or ''}")

    tag_matches = tokens & record_tags
    if tag_matches:
        score += TAG_BONUS * len(tag_matches)
        reasons.append("tag")

    entity_matches = tokens & record_entities
    if entity_matches:
        score += ENTITY_BONUS * len(entity_matches)
        reasons.append("entity")

    text_matches = tokens & record_text_tokens
    if text_matches:
        score += 0.25 * len(text_matches)
        reasons.append("text")

    relevance_reasons = list(reasons)
    if not relevance_reasons:
        return 0.0, []

    if scope_project and record.scope_project == scope_project:
        score += SCOPE_BONUS
        reasons.append("scope")
        if record.kind == "active_project_state":
            score += CAPSULE_SCOPE_BONUS
            reasons.append("project_capsule")
    elif scope_project and record.scope_project and record.scope_project != scope_project:
        score -= SCOPE_BONUS
        reasons.append("scope_mismatch")

    score += record.confidence * CONFIDENCE_WEIGHT
    score += record.importance * IMPORTANCE_WEIGHT
    score -= TRUST_PENALTIES.get(record.trust_level, 0.0)

    return score, reasons


def _query_tokens(query: str) -> set[str]:
    return {
        token
        for token in (_normalize_token(raw) for raw in re.findall(r"[\w:-]+", query.lower()))
        if token and token not in STOPWORDS
    }


def _expand_tokens(tokens: set[str]) -> set[str]:
    expanded = set(tokens)
    for token in tokens:
        expanded.update(ALIASES.get(token, set()))
    if "timed" in tokens and "out" in tokens:
        expanded.add("timeout")
    return expanded


def _normalize_token(token: str) -> str:
    return token.lower().strip()
