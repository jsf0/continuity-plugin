from __future__ import annotations

from continuity.models import ContextRecord
from continuity.record_quality import assess_record_quality, enrich_record_metadata


def _record(**overrides) -> ContextRecord:
    values = {
        "id": "r_quality",
        "kind": "project_convention",
        "title": "Guard proxy uses ruff and pytest",
        "summary": "guard-proxy development uses ruff for linting and pytest for regression tests.",
        "tags": ["python", "testing"],
        "entities": ["guard-proxy", "ruff", "pytest"],
        "trust_level": "explicit_user",
    }
    values.update(overrides)
    return ContextRecord.new(**values)


def test_assess_record_quality_accepts_anchored_record() -> None:
    assessment = assess_record_quality(_record(), facets=["software_project"])

    assert assessment.reject is False
    assert assessment.review_required is False
    assert "sparse_metadata" not in assessment.warnings
    assert assessment.tag_count == 2
    assert assessment.entity_count == 3


def test_assess_record_quality_warns_for_sparse_explicit_record() -> None:
    assessment = assess_record_quality(
        _record(tags=["user_preference"], entities=[], kind="user_preference"),
        facets=["personal_preference"],
    )

    assert assessment.reject is False
    assert assessment.review_required is False
    assert "sparse_metadata" in assessment.warnings
    assert "no_entities" in assessment.warnings


def test_assess_record_quality_requires_review_for_sparse_corpus_record() -> None:
    assessment = assess_record_quality(
        _record(tags=[], entities=[], trust_level="corpus_distilled"), facets=[]
    )

    assert assessment.reject is False
    assert assessment.review_required is True
    assert "sparse_metadata" in assessment.warnings


def test_assess_record_quality_flags_huge_entity_list() -> None:
    assessment = assess_record_quality(
        _record(entities=[f"Entity {index}" for index in range(40)]),
        facets=["software_project"],
    )

    assert "huge_entity_list" in assessment.warnings
    assert assessment.review_required is True


def test_enrich_record_metadata_merges_literal_entities_and_tags() -> None:
    record = _record(
        title="OpenBSD guard-proxy deployment",
        summary="guard-proxy uses tag:openbsd and rcctl restart during deployment.",
        tags=["deployment"],
        entities=[],
    )

    enriched, assessment = enrich_record_metadata(record)

    assert "deployment" in enriched.tags
    assert "openbsd" in enriched.tags
    assert "OpenBSD" in enriched.entities
    assert "guard-proxy" in enriched.entities
    assert assessment.derived_tag_count >= 1
    assert assessment.derived_entity_count >= 1
    assert enriched.quality["score"] == assessment.score


def test_enrich_record_metadata_deduplicates_case_insensitively() -> None:
    record = _record(
        title="OpenBSD OpenBSD",
        summary="OpenBSD uses tag:OpenBSD.",
        tags=["openbsd"],
        entities=["openbsd"],
    )

    enriched, _ = enrich_record_metadata(record)

    assert enriched.tags.count("openbsd") == 1
    assert len([entity for entity in enriched.entities if entity.casefold() == "openbsd"]) == 1


def test_enrich_record_metadata_stores_derived_facets_in_assessment() -> None:
    record = _record(
        title="FastAPI API framework choice",
        summary="The software project uses FastAPI for API routing.",
        tags=["api", "software"],
        entities=["FastAPI"],
    )

    _enriched, assessment = enrich_record_metadata(record)

    assert "software_project" in assessment.facets
    assert "unknown_or_empty_facets" not in assessment.warnings
