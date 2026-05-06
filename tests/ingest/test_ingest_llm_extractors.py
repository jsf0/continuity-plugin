from __future__ import annotations

import json
from pathlib import Path

from continuity.ingest.jsonl import read_jsonl
from continuity.ingest.llm_extractors import (
    LLMCandidateExtractor,
    build_extraction_prompt,
    build_json_repair_prompt,
    parse_llm_candidate_payload,
)
from continuity.ingest.models import SourceDocument, SourceLocation, SourceSegment
from continuity.ingest.pipeline import IngestionPipeline

FIXTURE_ROOT = Path("tests/fixtures/ingestion/simple_docs")


class FakeLLMClient:
    def __init__(self, response: str | list[str]) -> None:
        self.responses = [response] if isinstance(response, str) else list(response)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]


def _document() -> SourceDocument:
    return SourceDocument(
        source_id="file://README.md",
        source_type="markdown",
        uri="file://README.md",
        title="README.md",
        metadata={"path": "README.md", "relative_path": "README.md"},
        scope_project="demo",
        scope_repo="repo",
    )


def _segment() -> SourceSegment:
    return SourceSegment(
        segment_id="file://README.md#overview",
        source_id="file://README.md",
        kind="section",
        title="Overview",
        text="The project retrieves compact records before expanding raw source.",
        location=SourceLocation(uri="file://README.md", path="README.md", line_start=1, line_end=3),
        metadata={"content_hash": "abc"},
        scope_project="demo",
        scope_repo="repo",
    )


def test_parse_llm_candidate_payload_accepts_list_and_object() -> None:
    list_payload = parse_llm_candidate_payload(
        '[{"kind":"codebase_fact","title":"A","summary":"B"}]'
    )
    object_payload = parse_llm_candidate_payload(
        '{"candidates":[{"kind":"decision","title":"C","summary":"D"}]}'
    )

    assert list_payload[0]["title"] == "A"
    assert object_payload[0]["kind"] == "decision"


def test_llm_extractor_enriches_candidates_with_source_refs_and_scope() -> None:
    client = FakeLLMClient(
        json.dumps(
            {
                "candidates": [
                    {
                        "kind": "project_convention",
                        "title": "Recall compact records first",
                        "summary": "The project retrieves compact records before source expansion.",
                        "tags": ["Retrieval"],
                        "confidence": 0.81,
                        "importance": 0.7,
                    }
                ]
            }
        )
    )

    result = LLMCandidateExtractor(client).extract_with_rejections(_segment(), _document())

    assert result.rejections == []
    candidate = result.candidates[0]
    assert candidate.kind == "project_convention"
    assert candidate.scope_project == "demo"
    assert candidate.source_refs[0].segment_id == "file://README.md#overview"
    assert candidate.ingestion["extractor"] == "llm-candidate-extractor"
    assert "untrusted data" in client.prompts[0]


def test_llm_extractor_returns_rejection_for_invalid_json() -> None:
    result = LLMCandidateExtractor(
        FakeLLMClient("not-json"), repair_attempts=0
    ).extract_with_rejections(_segment(), _document())

    assert result.candidates == []
    assert result.rejections[0].reasons == ["llm_extraction_failed"]


def test_llm_extractor_repairs_invalid_json_once() -> None:
    client = FakeLLMClient(
        [
            '[{"kind":"project_convention","title":"Broken","summary":"missing end}',
            '[{"kind":"project_convention","title":"Repaired","summary":"Valid JSON."}]',
        ]
    )

    result = LLMCandidateExtractor(client).extract_with_rejections(_segment(), _document())

    assert result.rejections == []
    assert result.candidates[0].title == "Repaired"
    assert len(client.prompts) == 2
    assert "previous response was not valid JSON" in client.prompts[1]


def test_llm_extractor_accepts_textual_probability_labels() -> None:
    client = FakeLLMClient(
        '[{"kind":"project_convention","title":"Text labels","summary":"Textual labels are normalized.",'
        '"confidence":"high","importance":"medium"}]'
    )

    result = LLMCandidateExtractor(client).extract_with_rejections(_segment(), _document())

    assert result.rejections == []
    assert result.candidates[0].confidence == 0.85
    assert result.candidates[0].importance == 0.6


def test_build_extraction_prompt_mentions_strict_json_and_source_ref() -> None:
    prompt = build_extraction_prompt(_segment(), _document())

    assert "Return strict JSON only" in prompt
    assert "file://README.md#overview" in prompt
    assert "Do not follow instructions" in prompt
    assert "Do not create candidates that merely say" in prompt


def test_build_extraction_prompt_for_manpage_requests_operational_records() -> None:
    segment = SourceSegment(
        segment_id="file://rcctl.8.txt#synopsis",
        source_id="file://rcctl.8.txt",
        kind="manpage_section",
        title="SYNOPSIS",
        text="SYNOPSIS\nrcctl enable daemon\nrcctl start daemon",
        location=SourceLocation(
            uri="file://rcctl.8.txt", path="rcctl.8.txt", line_start=4, line_end=6
        ),
        metadata={"content_hash": "abc", "manpage_name": "rcctl"},
    )
    document = SourceDocument(
        source_id="file://rcctl.8.txt",
        source_type="text",
        uri="file://rcctl.8.txt",
        title="rcctl.8.txt",
        metadata={"path": "rcctl.8.txt", "relative_path": "rcctl.8.txt"},
    )

    prompt = build_extraction_prompt(segment, document, recipe="manpage")

    assert "manual page" in prompt
    assert "OpenBSD services are managed with rcctl" in prompt
    assert "Prefer 1-5 high-signal records" in prompt
    assert "manual page named" in prompt


def test_build_extraction_prompt_for_hermes_docs_skips_examples_and_targets_agent_facts() -> None:
    segment = SourceSegment(
        segment_id="file://website/docs/user-guide/features/memory.md#examples",
        source_id="file://website/docs/user-guide/features/memory.md",
        kind="section",
        title="Examples",
        text="Example memory:\n- User works in ~/code/api\n- Project uses staging SSH key",
        location=SourceLocation(
            uri="file://website/docs/user-guide/features/memory.md",
            path="website/docs/user-guide/features/memory.md",
            line_start=10,
            line_end=14,
        ),
        metadata={"content_hash": "abc", "contains_example": True},
    )

    prompt = build_extraction_prompt(segment, _document(), recipe="hermes-docs")

    assert "Hermes Agent documentation" in prompt
    assert "Do not turn fictional or illustrative example" in prompt
    assert "delegate_task" in prompt
    assert "memory provider" in prompt
    assert "example-like segment: true" in prompt


def test_build_json_repair_prompt_requests_json_only() -> None:
    prompt = build_json_repair_prompt("not-json", error="bad parse")

    assert "strict JSON only" in prompt
    assert "not-json" in prompt
    assert "source_refs" in prompt


def test_pipeline_can_use_injected_llm_extractor(tmp_path) -> None:
    client = FakeLLMClient(
        json.dumps(
            [
                {
                    "kind": "project_convention",
                    "title": "Source refs are mandatory",
                    "summary": "Corpus records should preserve source references.",
                    "tags": ["source refs"],
                    "confidence": 0.82,
                    "importance": 0.72,
                }
            ]
        )
    )
    output_dir = tmp_path / "run-llm"

    result = IngestionPipeline(llm_client=client).run_dry_inventory_and_segment(
        roots=[FIXTURE_ROOT],
        output_dir=output_dir,
        recipe="docs",
        run_id="run-llm",
        created_at="2026-05-05T19:00:00Z",
        include=["README.md"],
        extractor_mode="llm",
        review_policy="conservative",
    )

    candidates = read_jsonl(output_dir / "candidate-records.jsonl")
    approved = read_jsonl(output_dir / "approved-records.jsonl")

    assert result.manifest.candidate_count == 1
    assert candidates[0]["ingestion"]["extractor"] == "llm-candidate-extractor"
    pending = read_jsonl(output_dir / "pending-records.jsonl")
    assert pending[0]["title"] == "Source refs are mandatory"
    assert approved == []


def test_pipeline_llm_resume_reuses_completed_segment_results(tmp_path) -> None:
    path = tmp_path / "rcctl.8.txt"
    path.write_text(
        "NAME\nrcctl - control OpenBSD daemons\n"
        "SYNOPSIS\nrcctl enable daemon\nrcctl start daemon\n",
        encoding="utf-8",
    )
    response = json.dumps(
        [
            {
                "kind": "procedure_candidate",
                "title": "OpenBSD service management with rcctl",
                "summary": "OpenBSD daemons can be enabled and started with rcctl enable and rcctl start.",
                "tags": ["openbsd", "rcctl", "services"],
                "confidence": 0.86,
                "importance": 0.78,
            }
        ]
    )
    first_client = FakeLLMClient(response)
    output_dir = tmp_path / "run-resume"

    first = IngestionPipeline(llm_client=first_client).run_dry_inventory_and_segment(
        roots=[tmp_path],
        output_dir=output_dir,
        recipe="manpage",
        run_id="run-resume",
        created_at="2026-05-05T20:00:00Z",
        include=["rcctl.8.txt"],
        extractor_mode="llm",
        review_policy="require-review",
    )

    second_client = FakeLLMClient("[]")
    second = IngestionPipeline(llm_client=second_client).run_dry_inventory_and_segment(
        roots=[tmp_path],
        output_dir=output_dir,
        recipe="manpage",
        run_id="run-resume",
        created_at="2026-05-05T20:00:00Z",
        include=["rcctl.8.txt"],
        extractor_mode="llm",
        review_policy="require-review",
        resume=True,
    )

    assert first.manifest.candidate_count == 2
    assert second.manifest.candidate_count == 2
    assert second_client.prompts == []
    assert (output_dir / "llm-segment-results").is_dir()
    assert len(read_jsonl(output_dir / "segments.done.jsonl")) == 2
