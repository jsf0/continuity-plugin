"""Write-time enrichment and quality assessment for continuity records."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from .facets import facets_for_record
from .metadata_extraction import extract_metadata
from .models import ContextRecord

STRUCTURAL_TAGS = frozenset(
    {
        "built_in_memory",
        "memory_target:user",
        "memory_target:memory",
        "user_preference",
        "environment_fact",
        "project_convention",
        "lesson_learned",
        "decision",
        "active_project_state",
        "artifact_summary",
        "procedure_candidate",
        "codebase_fact",
        "paper_finding",
        "known_limitation",
        "glossary_term",
        "open_question",
    }
)
REVIEW_TRUST_LEVELS = frozenset(
    {
        "corpus_distilled",
        "internet_distilled",
        "corpus_raw_summary",
        "candidate_unreviewed",
        "remote_untrusted",
        "session_extracted",
    }
)
GENERIC_TITLES = frozenset(
    {
        "overview",
        "notes",
        "memory",
        "record",
        "hermes user memory",
        "hermes global memory",
    }
)
REVIEW_WARNINGS = frozenset(
    {"huge_entity_list", "example_like_source", "missing_source_ref", "unknown_or_empty_facets"}
)
ASSOCIATION_BLOCKING_WARNINGS = frozenset({"huge_entity_list", "sparse_metadata"})


@dataclass(frozen=True)
class MetadataQualityAssessment:
    tag_count: int
    entity_count: int
    derived_tag_count: int = 0
    derived_entity_count: int = 0
    facets: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    reject: bool = False
    review_required: bool = False
    score: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag_count": self.tag_count,
            "entity_count": self.entity_count,
            "derived_tag_count": self.derived_tag_count,
            "derived_entity_count": self.derived_entity_count,
            "facets": list(self.facets),
            "warnings": list(self.warnings),
            "reject": self.reject,
            "review_required": self.review_required,
            "score": self.score,
        }


def assess_record_quality(
    record: ContextRecord,
    *,
    derived_tags: list[str] | None = None,
    derived_entities: list[str] | None = None,
    facets: list[str] | None = None,
) -> MetadataQualityAssessment:
    """Return a conservative write-time quality assessment for a record."""

    warnings: list[str] = []
    tags = [tag for tag in record.tags if tag]
    entities = [entity for entity in record.entities if entity]
    meaningful_tags = [tag for tag in tags if tag not in STRUCTURAL_TAGS]
    title = " ".join(record.title.casefold().split())
    summary_tokens = re.findall(r"[a-z0-9]+", record.summary.casefold())
    source_refs = record.sources

    if not entities:
        warnings.append("no_entities")
    if not meaningful_tags and len(entities) < 1:
        warnings.append("sparse_metadata")
    if tags and not meaningful_tags:
        warnings.append("structural_tags_only")
    if title in GENERIC_TITLES:
        warnings.append("generic_title")
    if len(entities) > 24:
        warnings.append("huge_entity_list")
    if len(summary_tokens) < 6:
        warnings.append("low_information_summary")
    if not facets:
        warnings.append("unknown_or_empty_facets")
    if record.trust_level.startswith("corpus") and not source_refs:
        warnings.append("missing_source_ref")
    if any(_source_is_example_like(source.to_dict()) for source in source_refs):
        warnings.append("example_like_source")

    unique_warnings = tuple(dict.fromkeys(warnings))
    warning_set = set(unique_warnings)
    review_required = bool(warning_set & REVIEW_WARNINGS)
    if record.trust_level in REVIEW_TRUST_LEVELS and (
        "sparse_metadata" in warning_set or "unknown_or_empty_facets" in warning_set
    ):
        review_required = True

    score = max(0.0, round(1.0 - len(unique_warnings) * 0.12, 2))
    return MetadataQualityAssessment(
        tag_count=len(tags),
        entity_count=len(entities),
        derived_tag_count=len(derived_tags or []),
        derived_entity_count=len(derived_entities or []),
        facets=tuple(sorted(facets or [])),
        warnings=unique_warnings,
        reject=False,
        review_required=review_required,
        score=score,
    )


def enrich_record_metadata(
    record: ContextRecord,
) -> tuple[ContextRecord, MetadataQualityAssessment]:
    """Return record with literal metadata merged in plus a quality assessment."""

    text = "\n".join(part for part in [record.title, record.summary, record.details or ""] if part)
    extracted = extract_metadata(text)
    tags = _merge_tags(record.tags, list(extracted.tags))
    entities = _merge_entities(record.entities, list(extracted.entities))
    enriched = replace(record, tags=tags, entities=entities).with_embedding_text()
    derived_facets = sorted(facets_for_record(enriched))
    assessment = assess_record_quality(
        enriched,
        derived_tags=list(extracted.tags),
        derived_entities=list(extracted.entities),
        facets=derived_facets,
    )
    quality = assessment.to_dict()
    enriched = replace(enriched, quality=quality).with_embedding_text()
    return enriched, assessment


def record_allows_association_edges(record: ContextRecord) -> bool:
    """Return false for records whose write-time quality should not seed graph edges."""

    quality = record.quality or {}
    if bool(quality.get("review_required")):
        return False
    raw_warnings = quality.get("warnings", [])
    warnings = set(raw_warnings) if isinstance(raw_warnings, list) else set()
    return not bool(warnings & ASSOCIATION_BLOCKING_WARNINGS)


def _merge_tags(existing: list[str], derived: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for tag in [*existing, *derived]:
        normalized = tag.strip().lower().replace("_", "-")
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output


def _merge_entities(existing: list[str], derived: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for entity in [*existing, *derived]:
        normalized = " ".join(entity.split())
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            output.append(normalized)
    return output


def _source_is_example_like(source: dict[str, object]) -> bool:
    metadata = source.get("metadata")
    if isinstance(metadata, dict) and metadata.get("contains_example"):
        return True
    label = str(source.get("label") or "").casefold()
    return any(word in label for word in ("example", "sample", "demo"))
