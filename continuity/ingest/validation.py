"""Validation, safety, and normalization for ingestion candidates."""

from __future__ import annotations

import re
from dataclasses import replace

from continuity.ingest.models import CandidateRecord, Rejection
from continuity.security import redact_sensitive_text, truncate_text

_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(previous|all|above|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(the\s+)?system\s+prompt", re.IGNORECASE),
    re.compile(r"system\s+prompt\s+override", re.IGNORECASE),
    re.compile(r"do\s+not\s+tell\s+the\s+user", re.IGNORECASE),
    re.compile(r"exfiltrate\s+secrets?", re.IGNORECASE),
]

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{10,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s]+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
]


class CandidateNormalizer:
    """Normalize candidate records before review/import."""

    def __init__(self, *, max_summary_chars: int = 500, max_details_chars: int = 2000) -> None:
        self.max_summary_chars = max_summary_chars
        self.max_details_chars = max_details_chars

    def normalize(self, candidate: CandidateRecord) -> CandidateRecord:
        """Return a cleaned candidate record without mutating the original."""

        review = dict(candidate.review)
        if not review.get("status"):
            review["status"] = "pending_review"
            reasons = list(review.get("reasons") or [])
            if "normalizer_default" not in reasons:
                reasons.append("normalizer_default")
            review["reasons"] = reasons

        details = candidate.details
        if details is not None:
            details = truncate_text(
                redact_sensitive_text(details.strip()), max_chars=self.max_details_chars
            )

        return replace(
            candidate,
            title=" ".join(candidate.title.split()),
            summary=truncate_text(
                redact_sensitive_text(" ".join(candidate.summary.split())),
                max_chars=self.max_summary_chars,
            ),
            details=details,
            tags=_normalize_tags(candidate.tags),
            entities=_normalize_entities(candidate.entities),
            trust_level=candidate.trust_level or "corpus_distilled",
            review=review,
        )

    def normalize_dict(self, value: dict[str, object]) -> CandidateRecord | Rejection:
        """Parse and normalize a candidate dictionary, returning a rejection on validation failure."""

        item_id = str(value.get("candidate_id") or "unknown")
        try:
            return self.normalize(CandidateRecord.from_dict(value))
        except (TypeError, ValueError) as exc:
            return Rejection(
                item_id=item_id,
                item_type="candidate_record",
                reasons=["invalid_candidate"],
                metadata={"error": str(exc)},
            )


class SafetyGate:
    """Detect obviously unsafe candidate records before review/import."""

    def assess(self, candidate: CandidateRecord) -> Rejection | None:
        reasons: list[str] = []
        text = _candidate_text(candidate)
        if any(pattern.search(text) for pattern in _PROMPT_INJECTION_PATTERNS):
            reasons.append("prompt_injection_detected")
        if any(pattern.search(text) for pattern in _SECRET_PATTERNS):
            reasons.append("secret_detected")
        if candidate.trust_level.startswith("corpus") and not candidate.source_refs:
            reasons.append("missing_source_refs")
        if _is_example_derived(candidate):
            reasons.append("example_derived_candidate")
        if not reasons:
            return None
        return Rejection(
            item_id=candidate.candidate_id,
            item_type="candidate_record",
            reasons=reasons,
            metadata={"title": candidate.title, "trust_level": candidate.trust_level},
        )


def _candidate_text(candidate: CandidateRecord) -> str:
    return "\n".join(
        part for part in [candidate.title, candidate.summary, candidate.details or ""] if part
    )


def _is_example_derived(candidate: CandidateRecord) -> bool:
    return any(
        bool(source_ref.metadata.get("contains_example")) for source_ref in candidate.source_refs
    )


def _normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        value = re.sub(r"[^a-z0-9]+", "-", tag.strip().lower()).strip("-")
        if value and value not in seen:
            seen.add(value)
            normalized.append(value)
    return normalized


def _normalize_entities(entities: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for entity in entities:
        value = " ".join(entity.split())
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            normalized.append(value)
    return normalized
