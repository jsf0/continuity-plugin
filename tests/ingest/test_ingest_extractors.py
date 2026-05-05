from __future__ import annotations

from pathlib import Path

from continuity.ingest.extractors import (
    CodeOrConfigFactExtractor,
    EvalCaseGenerator,
    ProcedureCandidateExtractor,
    ProjectCapsuleExtractor,
)
from continuity.ingest.models import SourceDocument, SourceLocation, SourceSegment

FIXTURE_ROOT = Path("tests/fixtures/ingestion/simple_docs")


def _segment(
    *,
    segment_id: str = "file://README.md#project",
    source_id: str = "file://README.md",
    title: str = "Project Overview",
    text: str = "The project stores compact records with source references.",
    line_start: int = 1,
    line_end: int = 4,
) -> SourceSegment:
    return SourceSegment(
        segment_id=segment_id,
        source_id=source_id,
        kind="section",
        title=title,
        text=text,
        location=SourceLocation(
            uri=source_id, path="README.md", line_start=line_start, line_end=line_end
        ),
        metadata={"heading_path": [title], "content_hash": "abc"},
        scope_project="continuity-ingestion-fixture",
        scope_repo=str(FIXTURE_ROOT),
    )


def _document(source_id: str = "file://README.md", title: str = "README.md") -> SourceDocument:
    return SourceDocument(
        source_id=source_id,
        source_type="markdown",
        uri=source_id,
        title=title,
        metadata={"path": title, "relative_path": title, "sha256": "abc"},
        scope_project="continuity-ingestion-fixture",
        scope_repo=str(FIXTURE_ROOT),
        collection="simple-docs",
    )


def test_project_capsule_extractor_creates_artifact_summary_from_readme_segment() -> None:
    candidate = ProjectCapsuleExtractor().extract(_segment(), _document())[0]

    assert candidate.kind == "artifact_summary"
    assert candidate.title == "Project capsule: continuity-ingestion-fixture"
    assert "stores compact records" in candidate.summary
    assert candidate.scope_project == "continuity-ingestion-fixture"
    assert candidate.tags == ["project-capsule", "corpus-ingestion"]
    assert candidate.trust_level == "corpus_distilled"
    assert candidate.source_refs[0].uri == "file://README.md"
    assert candidate.source_refs[0].line_start == 1
    assert candidate.ingestion["extractor"] == "project-capsule"


def test_project_capsule_extractor_ignores_non_readme_sources() -> None:
    candidates = ProjectCapsuleExtractor().extract(
        _segment(source_id="file://docs/architecture.md"),
        _document(source_id="file://docs/architecture.md", title="architecture.md"),
    )

    assert candidates == []


def test_procedure_candidate_extractor_detects_release_checklist() -> None:
    segment = _segment(
        segment_id="file://docs/release.md#release-checklist",
        source_id="file://docs/release.md",
        title="Release checklist",
        text="1. Run formatting.\n2. Run linting.\n3. Run the test suite.\n4. Build the wheel.",
        line_start=3,
        line_end=8,
    )

    candidate = ProcedureCandidateExtractor().extract(
        segment, _document("file://docs/release.md", "release.md")
    )[0]

    assert candidate.kind == "procedure_candidate"
    assert candidate.title == "Procedure candidate: Release checklist"
    assert "Run formatting" in candidate.summary
    assert candidate.tags == ["procedure", "skill-candidate", "release"]
    assert candidate.importance >= 0.7
    assert candidate.source_refs[0].segment_id == "file://docs/release.md#release-checklist"


def test_procedure_candidate_extractor_ignores_noisy_segment() -> None:
    candidates = ProcedureCandidateExtractor().extract(
        _segment(title="Noisy Notes", text="Today I moved a paragraph around."),
        _document(),
    )

    assert candidates == []


def test_code_or_config_fact_extractor_detects_test_commands() -> None:
    segment = _segment(
        title="Testing",
        text="Run `uv run pytest tests/ -q` before release. Then run `uv run ruff check .`.",
    )

    candidates = CodeOrConfigFactExtractor().extract(segment, _document())

    assert [candidate.kind for candidate in candidates] == ["codebase_fact", "codebase_fact"]
    assert candidates[0].title == "Test command: uv run pytest tests/ -q"
    assert "uv run pytest tests/ -q" in candidates[0].summary
    assert candidates[0].tags == ["codebase-map", "test-command"]
    assert candidates[1].title == "Lint command: uv run ruff check ."
    assert candidates[1].tags == ["codebase-map", "lint-command"]


def test_eval_case_generator_creates_positive_eval_from_candidate() -> None:
    candidate = ProjectCapsuleExtractor().extract(_segment(), _document())[0]

    eval_case = EvalCaseGenerator().generate(candidate)

    assert (
        eval_case["query"]
        == "What should I know about Project capsule: continuity-ingestion-fixture?"
    )
    assert eval_case["expected_record_titles"] == [candidate.title]
    assert eval_case["expected_tags"] == ["project-capsule", "corpus-ingestion"]
    assert eval_case["source_candidate_ids"] == [candidate.candidate_id]
