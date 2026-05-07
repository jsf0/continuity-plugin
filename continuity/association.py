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

    reference_evidence = _source_reference_evidence(
        left, right, left_entities=left_entities, right_entities=right_entities
    )
    if reference_evidence is not None:
        return reference_evidence

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


def _source_reference_evidence(
    left: ContextRecord,
    right: ContextRecord,
    *,
    left_entities: set[str],
    right_entities: set[str],
) -> AssociationEvidence | None:
    left_refs = _outbound_reference_targets(left)
    right_refs = _outbound_reference_targets(right)
    left_identity = _record_identity_terms(left, left_entities)
    right_identity = _record_identity_terms(right, right_entities)

    left_to_right = tuple(sorted(left_refs & right_identity))
    right_to_left = tuple(sorted(right_refs & left_identity))
    matched = left_to_right or right_to_left
    if not matched:
        return None
    reasons = ["source_outbound_reference"]
    if left_to_right:
        reasons.append("left_references_right")
    if right_to_left:
        reasons.append("right_references_left")
    return AssociationEvidence(
        strength=0.72,
        edge_type="source_reference",
        shared_entities=matched,
        shared_tags=(),
        shared_terms=(),
        reasons=tuple(reasons),
    )


def _outbound_reference_targets(record: ContextRecord) -> set[str]:
    targets: set[str] = set()
    for source in record.sources:
        metadata = source.metadata or {}
        references = metadata.get("outbound_references")
        if not isinstance(references, list):
            continue
        for reference in references:
            if not isinstance(reference, dict):
                continue
            target = normalize_phrase(str(reference.get("target") or ""))
            raw = normalize_phrase(str(reference.get("raw") or ""))
            if target:
                targets.add(target)
            if raw:
                targets.add(raw)
    return targets


def _record_identity_terms(record: ContextRecord, entities: set[str]) -> set[str]:
    terms = set(entities)
    title = normalize_phrase(record.title)
    if title:
        terms.add(title)
    for source in record.sources:
        metadata = source.metadata or {}
        context = metadata.get("context")
        if not isinstance(context, dict):
            continue
        labels = context.get("labels")
        if not isinstance(labels, dict):
            continue
        for value in labels.values():
            label = normalize_phrase(str(value or ""))
            if label:
                terms.add(label)
    quality_context = record.quality.get("context") if isinstance(record.quality, dict) else None
    if isinstance(quality_context, dict):
        labels = quality_context.get("labels")
        if isinstance(labels, dict):
            for value in labels.values():
                label = normalize_phrase(str(value or ""))
                if label:
                    terms.add(label)
    return terms


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
