"""Retrieval evaluation helpers for corpus ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from continuity.ingest.jsonl import read_jsonl, write_jsonl
from continuity.ingest.models import CandidateRecord, stable_id
from continuity.retrieval import ContinuityRetriever
from continuity.store import ContinuityStore


@dataclass(frozen=True)
class EvalCase:
    """A retrieval eval case for imported corpus records."""

    eval_id: str
    query: str
    expected_record_titles: list[str]
    expected_tags: list[str]
    expected_top_k: int | None = None
    forbidden_record_titles: list[str] = field(default_factory=list)
    forbidden_tags: list[str] = field(default_factory=list)
    scope_project: str | None = None
    source_candidate_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "eval_id": self.eval_id,
            "query": self.query,
            "expected_record_titles": self.expected_record_titles,
            "expected_tags": self.expected_tags,
            "expected_top_k": self.expected_top_k,
            "forbidden_record_titles": self.forbidden_record_titles,
            "forbidden_tags": self.forbidden_tags,
            "scope_project": self.scope_project,
            "source_candidate_ids": self.source_candidate_ids,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> EvalCase:
        return cls(
            eval_id=str(value.get("eval_id") or ""),
            query=str(value.get("query") or ""),
            expected_record_titles=_string_list(value.get("expected_record_titles")),
            expected_tags=_string_list(value.get("expected_tags")),
            expected_top_k=_optional_int(value.get("expected_top_k")),
            forbidden_record_titles=_string_list(value.get("forbidden_record_titles")),
            forbidden_tags=_string_list(value.get("forbidden_tags")),
            scope_project=_optional_str(value.get("scope_project")),
            source_candidate_ids=_string_list(value.get("source_candidate_ids")),
        )


@dataclass(frozen=True)
class EvalCaseResult:
    """Result for one retrieval eval case."""

    eval_id: str
    query: str
    passed: bool
    matched_titles: list[str]
    missing_titles: list[str]
    top_k_failures: list[str]
    missing_tags: list[str]
    forbidden_title_matches: list[str]
    forbidden_matches: list[str]
    selected_titles: list[str]
    selected_tags: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "eval_id": self.eval_id,
            "query": self.query,
            "passed": self.passed,
            "matched_titles": self.matched_titles,
            "missing_titles": self.missing_titles,
            "top_k_failures": self.top_k_failures,
            "missing_tags": self.missing_tags,
            "forbidden_title_matches": self.forbidden_title_matches,
            "forbidden_matches": self.forbidden_matches,
            "selected_titles": self.selected_titles,
            "selected_tags": self.selected_tags,
        }


@dataclass(frozen=True)
class EvalRunResult:
    """Aggregate result for an eval file."""

    passed: bool
    total: int
    passed_count: int
    failed_count: int
    case_results: list[EvalCaseResult]


def generate_eval_case(candidate: CandidateRecord) -> EvalCase:
    """Generate a simple positive eval case from a candidate record."""

    return EvalCase(
        eval_id=stable_id("eval", candidate.candidate_id),
        query=f"What should I know about {candidate.title}?",
        expected_record_titles=[candidate.title],
        expected_tags=list(candidate.tags),
        forbidden_tags=[],
        scope_project=candidate.scope_project,
        source_candidate_ids=[candidate.candidate_id],
    )


class EvalRunner:
    """Run retrieval evals against a continuity store."""

    def __init__(self, store: ContinuityStore, *, limit: int = 10) -> None:
        self.store = store
        self.store.migrate()
        self.limit = limit

    def run_case(self, eval_case: EvalCase) -> EvalCaseResult:
        hits = ContinuityRetriever(self.store).search(
            eval_case.query,
            scope_project=eval_case.scope_project,
            limit=self.limit,
        )
        records = [hit.record for hit in hits]
        selected_titles = [record.title for record in records]
        selected_tags = _unique_tags(records)
        matched_titles = [
            title for title in eval_case.expected_record_titles if title in selected_titles
        ]
        missing_titles = [
            title for title in eval_case.expected_record_titles if title not in selected_titles
        ]
        top_k_titles = (
            selected_titles[: eval_case.expected_top_k]
            if eval_case.expected_top_k
            else selected_titles
        )
        top_k_failures = [
            title
            for title in eval_case.expected_record_titles
            if eval_case.expected_top_k and title in selected_titles and title not in top_k_titles
        ]
        missing_tags = [tag for tag in eval_case.expected_tags if tag not in selected_tags]
        forbidden_title_matches = [
            title for title in eval_case.forbidden_record_titles if title in selected_titles
        ]
        forbidden_matches = [tag for tag in eval_case.forbidden_tags if tag in selected_tags]
        passed = (
            not missing_titles
            and not top_k_failures
            and not missing_tags
            and not forbidden_title_matches
            and not forbidden_matches
        )
        return EvalCaseResult(
            eval_id=eval_case.eval_id,
            query=eval_case.query,
            passed=passed,
            matched_titles=matched_titles,
            missing_titles=missing_titles,
            top_k_failures=top_k_failures,
            missing_tags=missing_tags,
            forbidden_title_matches=forbidden_title_matches,
            forbidden_matches=forbidden_matches,
            selected_titles=selected_titles,
            selected_tags=selected_tags,
        )

    def run_file(
        self, evals_path: str | Path, *, report_path: str | Path | None = None
    ) -> EvalRunResult:
        cases = [EvalCase.from_dict(row) for row in read_jsonl(evals_path)]
        case_results = [self.run_case(eval_case) for eval_case in cases]
        passed_count = sum(1 for result in case_results if result.passed)
        aggregate = EvalRunResult(
            passed=passed_count == len(case_results),
            total=len(case_results),
            passed_count=passed_count,
            failed_count=len(case_results) - passed_count,
            case_results=case_results,
        )
        if report_path is not None:
            write_jsonl(report_path, [result.to_dict() for result in case_results])
        return aggregate


def _unique_tags(records: list[object]) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for record in records:
        for tag in getattr(record, "tags", []):
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
    return tags


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected a list")
    return [str(item) for item in value]


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    number = int(value)
    return number if number > 0 else None
