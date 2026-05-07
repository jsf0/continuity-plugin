"""Generic opaque context-label compatibility helpers.

The retrieval and ingestion layers use these helpers to compare arbitrary
key/value context labels (for example OS, customer, or language partitions)
without adding domain-specific behavior to runtime retrieval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .models import ContextRecord

_SAFE_LABEL_RE = re.compile(r"^[a-z0-9._:-]+$")
_COMPARISON_TERMS = frozenset({"all variants", "between", "compare", "difference", "versus", "vs"})


@dataclass(frozen=True)
class ContextLabelSet:
    """Normalized generic context labels plus policy key sets."""

    labels: dict[str, str] = field(default_factory=dict)
    partition_keys: frozenset[str] = frozenset()
    soft_keys: frozenset[str] = frozenset()
    identity_keys: frozenset[str] = frozenset()
    collision_risk: str = "normal"

    def __post_init__(self) -> None:
        normalized = _normalize_labels(self.labels)
        object.__setattr__(self, "labels", normalized)
        object.__setattr__(
            self, "partition_keys", _normalize_key_set(self.partition_keys, normalized)
        )
        object.__setattr__(self, "soft_keys", _normalize_key_set(self.soft_keys, normalized))
        object.__setattr__(
            self, "identity_keys", _normalize_key_set(self.identity_keys, normalized)
        )
        risk = _normalize_atom(self.collision_risk) or "normal"
        if risk not in {"normal", "high"}:
            risk = "normal"
        object.__setattr__(self, "collision_risk", risk)


@dataclass(frozen=True)
class ContextCompatibility:
    """Detailed result of comparing query/session labels with record labels."""

    matched: dict[str, str]
    conflicts: dict[str, tuple[str, str]]
    missing_query_keys: frozenset[str]
    missing_record_keys: frozenset[str]
    hard_conflict: bool
    missing_required_partition: bool
    missing_required_record: bool
    comparison_allowed: bool
    score_adjustment: float
    reasons: tuple[str, ...]

    @property
    def rejected(self) -> bool:
        """Return true when normal retrieval should withhold the record."""

        return (
            self.hard_conflict or self.missing_required_partition or self.missing_required_record
        ) and not self.comparison_allowed


def context_from_mapping(mapping: dict[str, object] | None) -> ContextLabelSet:
    """Build a normalized label set from a JSON-like mapping.

    Malformed values are ignored conservatively.  The function accepts either a
    direct context payload or an outer mapping containing a ``context`` key.
    """

    if not isinstance(mapping, dict):
        return ContextLabelSet()
    payload: object = mapping.get("context", mapping)
    if not isinstance(payload, dict):
        return ContextLabelSet()
    labels = payload.get("labels", {})
    return ContextLabelSet(
        labels=labels if isinstance(labels, dict) else {},
        partition_keys=_coerce_sequence(payload.get("partition_keys")),
        soft_keys=_coerce_sequence(payload.get("soft_keys")),
        identity_keys=_coerce_sequence(payload.get("identity_keys")),
        collision_risk=str(payload.get("collision_risk") or "normal"),
    )


def context_from_record(record: ContextRecord) -> ContextLabelSet:
    """Extract context labels from ``ContextRecord.quality['context']``."""

    return context_from_mapping(record.quality or {})


def context_to_mapping(label_set: ContextLabelSet) -> dict[str, object]:
    """Serialize a label set into the stable JSON-friendly context payload."""

    return {
        "labels": dict(sorted(label_set.labels.items())),
        "partition_keys": sorted(label_set.partition_keys),
        "soft_keys": sorted(label_set.soft_keys),
        "identity_keys": sorted(label_set.identity_keys),
        "collision_risk": label_set.collision_risk,
    }


def has_comparison_intent(query: str) -> bool:
    """Return true for generic comparison/enumeration wording."""

    text = query.lower()
    return any(term in text for term in _COMPARISON_TERMS)


def compare_contexts(
    query_context: ContextLabelSet | dict[str, object] | None,
    record_context: ContextLabelSet | dict[str, object] | None,
    *,
    comparison_intent: bool = False,
    allow_missing_partition: bool = False,
) -> ContextCompatibility:
    """Compare query/session context labels to a record's context labels."""

    query = _ensure_context(query_context)
    record = _ensure_context(record_context)
    reasons: list[str] = []
    matched: dict[str, str] = {}
    conflicts: dict[str, tuple[str, str]] = {}

    all_keys = set(query.labels) | set(record.labels)
    for key in sorted(all_keys):
        query_value = query.labels.get(key)
        record_value = record.labels.get(key)
        if query_value is None:
            continue
        if record_value is None:
            continue
        if query_value == record_value:
            matched[key] = record_value
            reasons.append(f"context_label_match:{key}")
        else:
            conflicts[key] = (query_value, record_value)
            if comparison_intent:
                reasons.append(f"comparison_context_conflict:{key}")
            else:
                reasons.append(f"context_label_conflict:{key}")

    hard_keys = (
        query.partition_keys | record.partition_keys | query.identity_keys | record.identity_keys
    )
    hard_conflict = bool(hard_keys & set(conflicts))

    missing_query_keys = frozenset(key for key in record.partition_keys if key not in query.labels)
    required_record_keys = query.partition_keys | query.identity_keys
    missing_record_keys = frozenset(
        key for key in required_record_keys if key in query.labels and key not in record.labels
    )
    missing_required_partition = (
        record.collision_risk == "high"
        and bool(record.partition_keys)
        and bool(missing_query_keys)
        and not allow_missing_partition
    )
    missing_required_record = bool(missing_record_keys) and not allow_missing_partition
    for key in sorted(missing_query_keys):
        reasons.append(f"missing_partition_context:{key}")
    for key in sorted(missing_record_keys):
        reasons.append(f"missing_record_context:{key}")

    score_adjustment = 0.0
    score_adjustment += 0.25 * len(matched)
    soft_conflicts = set(conflicts) & (query.soft_keys | record.soft_keys)
    score_adjustment -= 0.25 * len(soft_conflicts)
    if hard_conflict and not comparison_intent:
        score_adjustment -= 100.0
    if missing_required_partition and not comparison_intent:
        score_adjustment -= 100.0
    if missing_required_record and not comparison_intent:
        score_adjustment -= 100.0

    return ContextCompatibility(
        matched=matched,
        conflicts=conflicts,
        missing_query_keys=missing_query_keys,
        missing_record_keys=missing_record_keys,
        hard_conflict=hard_conflict,
        missing_required_partition=missing_required_partition,
        missing_required_record=missing_required_record,
        comparison_allowed=bool(comparison_intent),
        score_adjustment=score_adjustment,
        reasons=tuple(reasons),
    )


def _ensure_context(value: ContextLabelSet | dict[str, object] | None) -> ContextLabelSet:
    if isinstance(value, ContextLabelSet):
        return value
    if isinstance(value, dict):
        return context_from_mapping(value)
    return ContextLabelSet()


def _coerce_sequence(value: object) -> frozenset[str]:
    if isinstance(value, str):
        return frozenset({value})
    if not isinstance(value, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(str(item) for item in value)


def _normalize_labels(labels: dict[str, object]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for raw_key, raw_value in labels.items():
        key = _normalize_atom(str(raw_key))
        value = _normalize_atom(str(raw_value))
        if key and value:
            normalized[key] = value
    return normalized


def _normalize_key_set(values: object, labels: dict[str, str]) -> frozenset[str]:
    result = {_normalize_atom(str(value)) for value in _coerce_sequence(values)}
    return frozenset(value for value in result if value and (not labels or value in labels))


def _normalize_atom(value: str) -> str:
    text = value.strip().lower()
    if not text or not _SAFE_LABEL_RE.fullmatch(text):
        return ""
    return text
