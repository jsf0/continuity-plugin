"""Candidate quality scoring and filtering for corpus ingestion."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from continuity.ingest.models import CandidateRecord, Rejection

_HARD_REJECTION_REASONS = {
    "generic_existence_claim",
    "weak_procedure",
    "too_short_summary",
    "low_information_candidate",
}
_GENERIC_TITLES = {
    "overview",
    "introduction",
    "notes",
    "public logs",
    "data handling",
    "record keeping",
    "follow-up",
    "decisions",
    "open questions",
}
_EXISTENCE_PATTERNS = [
    re.compile(r"\ba procedure (named|titled)\b", re.IGNORECASE),
    re.compile(r"\ba (section|document|procedure|workflow) (named|titled|called)\b", re.IGNORECASE),
    re.compile(r"\bexists in the\b", re.IGNORECASE),
]


@dataclass(frozen=True)
class CandidateQualityAssessment:
    """Deterministic quality assessment for one candidate record."""

    candidate_id: str
    score: float
    warnings: list[str]
    reject: bool = False


class CandidateQualityGate:
    """Detect low-value candidate records before dedupe/review."""

    def assess(self, candidate: CandidateRecord) -> CandidateQualityAssessment:
        warnings: list[str] = []
        title = _normalize(candidate.title)
        summary = _normalize(candidate.summary)
        summary_tokens = _tokens(candidate.summary)

        if len(summary_tokens) < 5:
            warnings.append("too_short_summary")
        if candidate.kind == "procedure_candidate" and _has_existence_claim(candidate.summary):
            warnings.extend(["weak_procedure", "generic_existence_claim"])
        elif _has_existence_claim(candidate.summary) and len(summary_tokens) <= 12:
            warnings.append("generic_existence_claim")
        if title in _GENERIC_TITLES and candidate.kind != "glossary_term":
            warnings.append("generic_title")
        if _summary_repeats_title(title, summary, summary_tokens):
            warnings.append("summary_repeats_title")
        if len(summary_tokens) < 8 and not candidate.tags and not candidate.entities:
            warnings.append("low_information_candidate")
        if not candidate.tags and not candidate.entities:
            warnings.append("sparse_metadata")
        elif not candidate.entities:
            warnings.append("no_entities")

        unique_warnings = _unique(warnings)
        score = max(0.0, 1.0 - len(unique_warnings) * 0.18)
        reject = any(reason in _HARD_REJECTION_REASONS for reason in unique_warnings)
        return CandidateQualityAssessment(
            candidate_id=candidate.candidate_id,
            score=round(score, 2),
            warnings=unique_warnings,
            reject=reject,
        )

    def apply(self, candidate: CandidateRecord) -> CandidateRecord | Rejection:
        """Return a quality-annotated candidate or a structured rejection."""

        assessment = self.assess(candidate)
        if assessment.reject:
            return Rejection(
                item_id=candidate.candidate_id,
                item_type="candidate_record",
                reasons=["quality_gate_rejected", *assessment.warnings],
                metadata={"title": candidate.title, "quality_score": assessment.score},
            )
        if not assessment.warnings:
            return candidate
        ingestion = dict(candidate.ingestion)
        ingestion["quality"] = {
            "score": assessment.score,
            "warnings": assessment.warnings,
        }
        # Keep warning-bearing candidates review-first by lowering auto-approval odds.
        return replace(candidate, ingestion=ingestion, confidence=min(candidate.confidence, 0.74))


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())


def _has_existence_claim(summary: str) -> bool:
    return any(pattern.search(summary) for pattern in _EXISTENCE_PATTERNS)


def _summary_repeats_title(title: str, summary: str, summary_tokens: list[str]) -> bool:
    if not title or not summary:
        return False
    if summary == title:
        return True
    title_tokens = set(_tokens(title))
    if not title_tokens:
        return False
    summary_token_set = set(summary_tokens)
    overlap = len(title_tokens & summary_token_set) / len(title_tokens)
    return overlap >= 0.8 and len(summary_tokens) <= len(title_tokens) + 4


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
