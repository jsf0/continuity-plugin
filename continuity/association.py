"""Association graph scoring derived from corpus statistics."""

from __future__ import annotations

from dataclasses import dataclass

from .models import ContextRecord
from .vocabulary import CorpusTermStats, normalize_phrase, tokenize_text, weighted_jaccard

ASSOCIATION_STRUCTURAL_TERMS = frozenset(
    {
        "active project state",
        "built in memory",
        "environment fact",
        "global",
        "hermes memory",
        "memory",
        "memory target memory",
        "memory target user",
        "preference",
        "project",
        "project convention",
        "project status",
        "status",
        "user",
        "user preference",
    }
)


@dataclass(frozen=True)
class AssociationEvidence:
    strength: float
    edge_type: str
    shared_entities: tuple[str, ...]
    shared_tags: tuple[str, ...]
    shared_terms: tuple[str, ...]
    reasons: tuple[str, ...]


def association_evidence(
    left: ContextRecord,
    right: ContextRecord,
    *,
    stats: CorpusTermStats | None = None,
) -> AssociationEvidence:
    left_entities = _value_tokens(left.entities)
    right_entities = _value_tokens(right.entities)
    left_tags = _value_tokens(left.tags)
    right_tags = _value_tokens(right.tags)
    left_text = _text_tokens(left)
    right_text = _text_tokens(right)

    if _only_generic_mirror_overlap(
        left, right, left_entities, right_entities, left_tags, right_tags
    ):
        return AssociationEvidence(
            0.0, "generic_mirror_overlap", (), (), (), ("only_generic_mirror_overlap",)
        )

    entity_overlap = weighted_jaccard(left_entities, right_entities, stats)
    tag_overlap = weighted_jaccard(left_tags, right_tags, stats)
    text_overlap = weighted_jaccard(left_text, right_text, stats)

    shared_entities = tuple(sorted(left_entities & right_entities))
    shared_tags = tuple(sorted(left_tags & right_tags))
    shared_terms = tuple(sorted((left_text & right_text) - set(shared_entities) - set(shared_tags)))

    strength = min(
        1.0,
        (0.35 if entity_overlap > 0 else 0.0)
        + (0.15 if tag_overlap > 0 else 0.0)
        + entity_overlap * 0.6
        + tag_overlap * 0.55
        + text_overlap * 0.3,
    )
    if entity_overlap > 0:
        edge_type = "entity_overlap"
    elif tag_overlap > 0:
        edge_type = "tag_overlap"
    elif text_overlap > 0:
        edge_type = "text_overlap"
    else:
        edge_type = "combined"

    reasons: list[str] = []
    if shared_entities:
        reasons.append("shared_entities")
    if shared_tags:
        reasons.append("shared_tags")
    if shared_terms:
        reasons.append("shared_text_terms")
    if stats is not None:
        reasons.append("idf_weighted")

    return AssociationEvidence(
        strength=strength,
        edge_type=edge_type,
        shared_entities=shared_entities,
        shared_tags=shared_tags,
        shared_terms=shared_terms[:20],
        reasons=tuple(reasons),
    )


def association_strength(
    left: ContextRecord, right: ContextRecord, *, stats: CorpusTermStats | None = None
) -> tuple[float, str]:
    evidence = association_evidence(left, right, stats=stats)
    return evidence.strength, evidence.edge_type


def _value_tokens(values: list[str]) -> set[str]:
    return {
        token
        for value in values
        if (token := normalize_phrase(value)) and token not in ASSOCIATION_STRUCTURAL_TERMS
    }


def _text_tokens(record: ContextRecord) -> set[str]:
    text = " ".join(
        [record.title, record.summary, record.details or "", *record.tags, *record.entities]
    )
    return {
        token
        for token in tokenize_text(text)
        if len(token) > 2 and token not in ASSOCIATION_STRUCTURAL_TERMS
    }


def _only_generic_mirror_overlap(
    left: ContextRecord,
    right: ContextRecord,
    left_entities: set[str],
    right_entities: set[str],
    left_tags: set[str],
    right_tags: set[str],
) -> bool:
    if not (_is_builtin_mirror(left) and _is_builtin_mirror(right)):
        return False
    meaningful_entity_overlap = {
        token
        for token in left_entities & right_entities
        if token not in ASSOCIATION_STRUCTURAL_TERMS
    }
    meaningful_tag_overlap = {
        token for token in left_tags & right_tags if token not in ASSOCIATION_STRUCTURAL_TERMS
    }
    return not meaningful_entity_overlap and not meaningful_tag_overlap


def _is_builtin_mirror(record: ContextRecord) -> bool:
    return record.trust_level == "built_in_memory_mirror" and record.title.lower() in {
        "hermes global memory",
        "hermes user memory",
    }
