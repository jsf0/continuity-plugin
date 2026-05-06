from __future__ import annotations

from continuity.ingest.eval import EvalCase, EvalRunner, generate_eval_case
from continuity.ingest.importer import ContinuityImporter
from continuity.ingest.jsonl import read_jsonl, write_jsonl
from continuity.ingest.models import CandidateRecord, SourceRef
from continuity.store import ContinuityStore


def _candidate(
    candidate_id: str = "cand_eval", *, tags: list[str] | None = None
) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=candidate_id,
        kind="artifact_summary",
        title="Project capsule: eval fixture",
        summary="The eval fixture stores compact source-linked records for ingestion testing.",
        scope_project="eval-fixture",
        tags=tags or ["project-capsule", "corpus-ingestion"],
        entities=["Eval Fixture"],
        confidence=0.9,
        importance=0.8,
        source_refs=[
            SourceRef(type="file", uri="file://README.md", segment_id="file://README.md#readme")
        ],
    )


def test_generate_eval_case_from_candidate() -> None:
    candidate = _candidate()

    eval_case = generate_eval_case(candidate)

    assert isinstance(eval_case, EvalCase)
    assert eval_case.eval_id.startswith("ing_")
    assert eval_case.query == "What should I know about Project capsule: eval fixture?"
    assert eval_case.expected_record_titles == [candidate.title]
    assert eval_case.expected_tags == ["project-capsule", "corpus-ingestion"]
    assert eval_case.scope_project == "eval-fixture"
    assert eval_case.source_candidate_ids == ["cand_eval"]
    assert EvalCase.from_dict(eval_case.to_dict()) == eval_case


def test_eval_runner_passes_when_expected_title_and_tags_are_found(tmp_path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    candidate = _candidate()
    ContinuityImporter(store).import_records([candidate], dry_run=False)
    eval_case = generate_eval_case(candidate)

    result = EvalRunner(store).run_case(eval_case)

    assert result.passed is True
    assert result.matched_titles == [candidate.title]
    assert result.missing_titles == []
    assert result.missing_tags == []
    assert result.forbidden_matches == []


def test_eval_runner_fails_for_missing_expected_title(tmp_path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    ContinuityImporter(store).import_records([_candidate()], dry_run=False)
    eval_case = EvalCase(
        eval_id="eval_missing",
        query="What should I know about nonexistent records?",
        expected_record_titles=["Not present"],
        expected_tags=[],
    )

    result = EvalRunner(store).run_case(eval_case)

    assert result.passed is False
    assert result.missing_titles == ["Not present"]


def test_eval_runner_fails_when_forbidden_tag_is_retrieved(tmp_path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    candidate = _candidate(tags=["project-capsule", "forbidden-noise"])
    ContinuityImporter(store).import_records([candidate], dry_run=False)
    eval_case = EvalCase(
        eval_id="eval_forbidden",
        query="What should I know about eval fixture?",
        expected_record_titles=[candidate.title],
        expected_tags=["project-capsule"],
        forbidden_tags=["forbidden-noise"],
    )

    result = EvalRunner(store).run_case(eval_case)

    assert result.passed is False
    assert result.forbidden_matches == ["forbidden-noise"]


def test_eval_runner_runs_jsonl_file_and_writes_report(tmp_path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    candidate = _candidate()
    ContinuityImporter(store).import_records([candidate], dry_run=False)
    evals_path = tmp_path / "retrieval-evals.jsonl"
    report_path = tmp_path / "eval-report.json"
    write_jsonl(evals_path, [generate_eval_case(candidate).to_dict()])

    result = EvalRunner(store).run_file(evals_path, report_path=report_path)

    assert result.passed is True
    assert result.total == 1
    assert result.passed_count == 1
    report_rows = read_jsonl(report_path)
    assert report_rows[0]["passed"] is True


def test_eval_runner_fails_when_expected_title_is_not_in_required_top_k(tmp_path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    noisy = _candidate(candidate_id="cand_noisy", tags=["corpus-ingestion"])
    expected = CandidateRecord(
        candidate_id="cand_expected",
        kind="artifact_summary",
        title="Specific eval fixture behavior",
        summary="Specific behavior for retrieval precision testing.",
        scope_project="eval-fixture",
        tags=["corpus-ingestion"],
        entities=["Eval Fixture"],
        confidence=0.9,
        importance=0.8,
        source_refs=[SourceRef(type="file", uri="file://specific.md")],
    )
    ContinuityImporter(store).import_records([noisy, expected], dry_run=False)
    eval_case = EvalCase(
        eval_id="eval_top_k",
        query="What should I know about eval fixture?",
        expected_record_titles=[expected.title],
        expected_tags=[],
        expected_top_k=1,
    )

    result = EvalRunner(store).run_case(eval_case)

    assert result.passed is False
    assert result.top_k_failures == [expected.title]


def test_eval_runner_fails_when_forbidden_title_is_retrieved(tmp_path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    candidate = _candidate()
    ContinuityImporter(store).import_records([candidate], dry_run=False)
    eval_case = EvalCase(
        eval_id="eval_forbidden_title",
        query="What should I know about eval fixture?",
        expected_record_titles=[],
        expected_tags=[],
        forbidden_record_titles=[candidate.title],
    )

    result = EvalRunner(store).run_case(eval_case)

    assert result.passed is False
    assert result.forbidden_title_matches == [candidate.title]


def test_eval_runner_uses_continuity_retriever_query_expansion(tmp_path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    candidate = CandidateRecord(
        candidate_id="cand_delegate_timeout",
        kind="lesson_learned",
        title="delegate_task timeout behavior",
        summary="delegate_task can time out before child agents report API calls.",
        scope_project="eval-fixture",
        tags=["delegate_task", "timeout"],
        entities=["api_calls:0"],
        confidence=0.9,
        importance=0.8,
        source_refs=[SourceRef(type="file", uri="file://delegation.md")],
    )
    ContinuityImporter(store).import_records([candidate], dry_run=False)
    eval_case = EvalCase(
        eval_id="eval_alias_expansion",
        query="what happened when the subagent got stuck",
        expected_record_titles=[candidate.title],
        expected_tags=["delegate-task"],
        scope_project="eval-fixture",
    )

    result = EvalRunner(store).run_case(eval_case)

    assert result.passed is True
    assert result.matched_titles == [candidate.title]
