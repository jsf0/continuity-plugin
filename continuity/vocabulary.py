"""Corpus-derived vocabulary statistics for retrieval.

This module deliberately avoids domain-specific synonym lists.  It computes
which terms are rare or generic from the records currently in the store.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from .models import ContextRecord

STRUCTURAL_GENERIC_TERMS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "for",
        "has",
        "have",
        "in",
        "is",
        "memory target memory",
        "memory target user",
        "of",
        "on",
        "or",
        "personal",
        "project convention",
        "that",
        "the",
        "to",
        "user",
        "uses",
        "with",
    }
)


@dataclass(frozen=True)
class CorpusTermStats:
    """Document-frequency statistics over continuity records."""

    document_count: int
    term_document_frequency: dict[str, int]
    tag_document_frequency: dict[str, int]
    entity_document_frequency: dict[str, int]

    @classmethod
    def from_records(cls, records: Iterable[ContextRecord]) -> CorpusTermStats:
        docs = list(records)
        term_df: Counter[str] = Counter()
        tag_df: Counter[str] = Counter()
        entity_df: Counter[str] = Counter()
        for record in docs:
            term_df.update(_record_terms(record))
            tag_df.update(normalize_phrase(tag) for tag in record.tags if normalize_phrase(tag))
            entity_df.update(
                normalize_phrase(entity) for entity in record.entities if normalize_phrase(entity)
            )
        return cls(
            document_count=len(docs),
            term_document_frequency=dict(term_df),
            tag_document_frequency=dict(tag_df),
            entity_document_frequency=dict(entity_df),
        )

    def document_frequency(self, term: str) -> int:
        normalized = normalize_phrase(term)
        return max(
            self.term_document_frequency.get(normalized, 0),
            self.tag_document_frequency.get(normalized, 0),
            self.entity_document_frequency.get(normalized, 0),
        )

    def idf(self, term: str) -> float:
        """Return smoothed inverse document frequency for a term."""

        if self.document_count <= 0:
            return 0.0
        df = self.document_frequency(term)
        return math.log((self.document_count + 1) / (df + 1)) + 1.0

    def is_generic(self, term: str, *, max_document_fraction: float = 0.35) -> bool:
        normalized = normalize_phrase(term)
        if not normalized or normalized in STRUCTURAL_GENERIC_TERMS:
            return True
        if self.document_count < 4:
            return normalized in STRUCTURAL_GENERIC_TERMS
        return (self.document_frequency(normalized) / self.document_count) > max_document_fraction


def normalize_phrase(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def tokenize_text(value: str) -> set[str]:
    tokens: set[str] = set()
    for raw in re.findall(r"[\w:-]+", value.lower()):
        normalized = normalize_phrase(raw)
        if normalized and len(normalized) > 1:
            tokens.add(normalized)
    return tokens


def _record_terms(record: ContextRecord) -> set[str]:
    text = " ".join(
        [
            record.title,
            record.summary,
            record.details or "",
            *record.tags,
            *record.entities,
        ]
    )
    return tokenize_text(text)


def weighted_jaccard(left: set[str], right: set[str], stats: CorpusTermStats | None) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    intersection = left & right
    if stats is None:
        return len(intersection) / len(union)
    numerator = sum(stats.idf(term) for term in intersection)
    denominator = sum(stats.idf(term) for term in union)
    return numerator / denominator if denominator else 0.0
