from __future__ import annotations

from continuity.context_labels import (
    ContextLabelSet,
    compare_contexts,
    context_from_mapping,
    context_from_record,
    context_to_mapping,
)
from continuity.models import ContextRecord


def test_partition_label_match_is_compatible() -> None:
    query = ContextLabelSet(labels={"OS": " OpenBSD "}, partition_keys={"os"})
    record = ContextLabelSet(labels={"os": "openbsd"}, partition_keys={"os"}, collision_risk="high")

    result = compare_contexts(query, record)

    assert result.rejected is False
    assert result.matched == {"os": "openbsd"}
    assert result.hard_conflict is False
    assert "context_label_match:os" in result.reasons
    assert result.score_adjustment > 0


def test_partition_label_conflict_is_hard_conflict() -> None:
    query = ContextLabelSet(labels={"os": "openbsd"}, partition_keys={"os"})
    record = ContextLabelSet(labels={"os": "linux"}, partition_keys={"os"}, collision_risk="high")

    result = compare_contexts(query, record)

    assert result.rejected is True
    assert result.hard_conflict is True
    assert result.conflicts == {"os": ("openbsd", "linux")}
    assert "context_label_conflict:os" in result.reasons


def test_missing_partition_on_high_collision_record_is_required_context_missing() -> None:
    record = ContextLabelSet(labels={"os": "openbsd"}, partition_keys={"os"}, collision_risk="high")

    result = compare_contexts(ContextLabelSet(), record)

    assert result.rejected is True
    assert result.missing_required_partition is True
    assert result.missing_query_keys == frozenset({"os"})
    assert "missing_partition_context:os" in result.reasons


def test_soft_label_conflict_downranks_without_rejecting() -> None:
    query = ContextLabelSet(labels={"version": "7.5"}, soft_keys={"version"})
    record = ContextLabelSet(labels={"version": "7.6"}, soft_keys={"version"})

    result = compare_contexts(query, record)

    assert result.rejected is False
    assert result.hard_conflict is False
    assert result.score_adjustment < 0
    assert result.conflicts == {"version": ("7.5", "7.6")}


def test_comparison_intent_allows_partition_conflict_with_reason() -> None:
    query = ContextLabelSet(labels={"customer": "acme"}, partition_keys={"customer"})
    record = ContextLabelSet(
        labels={"customer": "globex"}, partition_keys={"customer"}, collision_risk="high"
    )

    result = compare_contexts(query, record, comparison_intent=True)

    assert result.rejected is False
    assert result.hard_conflict is True
    assert result.comparison_allowed is True
    assert "comparison_context_conflict:customer" in result.reasons


def test_opaque_keys_are_not_special_cased() -> None:
    query = ContextLabelSet(labels={"language": "rust"}, partition_keys={"language"})
    record = ContextLabelSet(
        labels={"language": "python"}, partition_keys={"language"}, collision_risk="high"
    )

    result = compare_contexts(query, record)

    assert result.rejected is True
    assert result.conflicts == {"language": ("rust", "python")}


def test_context_mapping_helpers_ignore_malformed_values() -> None:
    context = context_from_mapping(
        {
            "context": {
                "labels": {" OS ": " OpenBSD ", "bad key": "ignored", "empty": ""},
                "partition_keys": ["os", "missing"],
                "soft_keys": "os",
                "identity_keys": ["BAD KEY", "os"],
                "collision_risk": "high",
            }
        }
    )

    assert context == ContextLabelSet(
        labels={"os": "openbsd"},
        partition_keys=frozenset({"os"}),
        soft_keys=frozenset({"os"}),
        identity_keys=frozenset({"os"}),
        collision_risk="high",
    )
    assert context_to_mapping(context) == {
        "labels": {"os": "openbsd"},
        "partition_keys": ["os"],
        "soft_keys": ["os"],
        "identity_keys": ["os"],
        "collision_risk": "high",
    }


def test_context_from_record_reads_quality_context() -> None:
    record = ContextRecord.new(
        id="r_context",
        kind="artifact_summary",
        title="context record",
        summary="stores generic context labels",
        quality={"context": {"labels": {"customer": "acme"}, "partition_keys": ["customer"]}},
    )

    assert context_from_record(record) == ContextLabelSet(
        labels={"customer": "acme"}, partition_keys=frozenset({"customer"})
    )
