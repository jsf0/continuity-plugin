"""Dry-run ingestion pipeline orchestration."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

from continuity.context_labels import ContextLabelSet, context_from_mapping, context_to_mapping
from continuity.ingest.connectors import LocalFilesConnector
from continuity.ingest.dedupe import BasicDeduper
from continuity.ingest.eval import EvalCase, generate_eval_case
from continuity.ingest.extractors import (
    CodeOrConfigFactExtractor,
    ProcedureCandidateExtractor,
    ProjectCapsuleExtractor,
)
from continuity.ingest.jsonl import write_jsonl
from continuity.ingest.llm_extractors import (
    CommandLLMClient,
    LLMCandidateExtractor,
    LLMClient,
    LLMExtractionResult,
)
from continuity.ingest.models import (
    CandidateRecord,
    IngestionRunManifest,
    Rejection,
    SourceDocument,
    SourceSegment,
    stable_hash,
)
from continuity.ingest.parsers import parser_for_document
from continuity.ingest.quality import CandidateQualityGate
from continuity.ingest.reports import build_ingestion_stats, render_dry_run_report
from continuity.ingest.review import ReviewPolicy, ReviewResult, write_review_artifacts
from continuity.ingest.segmenters import HeadingSectionSegmenter, ManPageSectionSegmenter
from continuity.ingest.validation import CandidateNormalizer, SafetyGate

_PARSEABLE_SOURCE_TYPES = {"markdown", "rst", "text", "manpage"}


@dataclass(frozen=True)
class PipelineResult:
    """Artifacts produced by a dry-run ingestion pipeline."""

    output_dir: Path
    manifest: IngestionRunManifest
    documents: list[SourceDocument]
    segments: list[SourceSegment]
    candidates: list[CandidateRecord] = field(default_factory=list)
    merged_candidates: list[CandidateRecord] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    review_result: ReviewResult | None = None
    eval_cases: list[EvalCase] = field(default_factory=list)


class IngestionPipeline:
    """Coordinate discovery, extraction, review, and dry-run artifact writing."""

    def __init__(
        self,
        *,
        connector: LocalFilesConnector | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.connector = connector or LocalFilesConnector()
        self.llm_client = llm_client

    def run_dry_inventory_and_segment(
        self,
        *,
        roots: Iterable[str | Path],
        output_dir: str | Path,
        recipe: str,
        run_id: str | None = None,
        created_at: str | None = None,
        include: Iterable[str] | None = None,
        exclude: Iterable[str] | None = None,
        project: str | None = None,
        repo: str | None = None,
        collection: str | None = None,
        review_policy: str = "conservative",
        extractor_mode: str = "deterministic",
        llm_command: str | None = None,
        resume: bool = False,
        context: dict[str, object] | ContextLabelSet | None = None,
    ) -> PipelineResult:
        """Run a dry corpus ingestion pipeline and write review-first artifacts.

        Despite the historical method name, this remains a dry run: it performs
        discovery, parsing, segmentation, deterministic extraction, validation,
        dedupe, review splitting, and eval generation, but never imports records.
        """

        root_paths = [Path(root) for root in roots]
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        timestamp = created_at or _utc_now()
        effective_run_id = run_id or f"run-{timestamp.replace(':', '').replace('-', '')}"
        config_hash = stable_hash(
            {
                "roots": [str(root) for root in root_paths],
                "recipe": recipe,
                "include": list(include or []),
                "exclude": list(exclude or []),
                "project": project,
                "repo": repo,
                "collection": collection,
                "review_policy": review_policy,
                "extractor_mode": extractor_mode,
                "context": _normalize_context(context),
            }
        )

        documents = self._discover_documents(
            root_paths,
            include=include,
            exclude=exclude,
            project=project,
            repo=repo,
            collection=collection,
        )
        documents = _attach_context_to_documents(documents, context)
        segments = self._segment_documents(documents, recipe=recipe)
        segments = _attach_context_to_segments(segments, context)
        candidates, rejections = self._extract_and_validate(
            documents,
            segments,
            extractor_mode=extractor_mode,
            llm_command=llm_command,
            recipe=recipe,
            output_path=output_path,
            resume=resume,
        )
        dedupe_result = BasicDeduper().dedupe(candidates)
        all_rejections = [*rejections, *dedupe_result.rejections]
        review_result = write_review_artifacts(
            output_path,
            candidates=dedupe_result.accepted,
            raw_candidates=candidates,
            rejections=all_rejections,
            policy=ReviewPolicy(review_policy),
        )
        eval_cases = [generate_eval_case(candidate) for candidate in review_result.approved]

        manifest = IngestionRunManifest(
            run_id=effective_run_id,
            created_at=timestamp,
            recipe=recipe,
            input_roots=[str(root) for root in root_paths],
            config_hash=config_hash,
            source_count=len(documents),
            segment_count=len(segments),
            candidate_count=len(candidates),
            approved_count=len(review_result.approved),
            imported_count=0,
            rejected_count=len(all_rejections),
            output_dir=str(output_path),
        )

        _write_manifest(output_path / "manifest.json", manifest)
        write_jsonl(output_path / "inventory.jsonl", [document.to_dict() for document in documents])
        write_jsonl(output_path / "segments.jsonl", [segment.to_dict() for segment in segments])
        write_jsonl(output_path / "retrieval-evals.jsonl", [case.to_dict() for case in eval_cases])
        stats = build_ingestion_stats(
            manifest=manifest,
            documents=documents,
            segments=segments,
            candidates=candidates,
            merged_candidates=dedupe_result.accepted,
            rejections=all_rejections,
            review_result=review_result,
        )
        (output_path / "ingestion-stats.json").write_text(
            json.dumps(stats, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output_path / "import-report.md").write_text(
            render_dry_run_report(manifest), encoding="utf-8"
        )

        return PipelineResult(
            output_dir=output_path,
            manifest=manifest,
            documents=documents,
            segments=segments,
            candidates=candidates,
            merged_candidates=dedupe_result.accepted,
            rejections=all_rejections,
            review_result=review_result,
            eval_cases=eval_cases,
        )

    def _discover_documents(
        self,
        root_paths: list[Path],
        *,
        include: Iterable[str] | None,
        exclude: Iterable[str] | None,
        project: str | None,
        repo: str | None,
        collection: str | None,
    ) -> list[SourceDocument]:
        documents: list[SourceDocument] = []
        for root in root_paths:
            documents.extend(
                document
                for document in self.connector.discover(
                    root,
                    include=include,
                    exclude=exclude,
                    project=project,
                    repo=repo or str(root),
                    collection=collection,
                )
                if document.source_type in _PARSEABLE_SOURCE_TYPES
            )
        return documents

    def _segment_documents(
        self, documents: list[SourceDocument], *, recipe: str
    ) -> list[SourceSegment]:
        segments: list[SourceSegment] = []
        segmenter = (
            ManPageSectionSegmenter() if _is_manpage_recipe(recipe) else HeadingSectionSegmenter()
        )
        for document in documents:
            parsed = parser_for_document(document, recipe=recipe).parse(document)
            segments.extend(segmenter.segment(parsed, document))
        return segments

    def _extract_and_validate(
        self,
        documents: list[SourceDocument],
        segments: list[SourceSegment],
        *,
        extractor_mode: str,
        llm_command: str | None,
        recipe: str,
        output_path: Path,
        resume: bool,
    ) -> tuple[list[CandidateRecord], list[Rejection]]:
        document_by_id = {document.source_id: document for document in documents}
        extractors = self._build_extractors(extractor_mode, llm_command, recipe=recipe)
        normalizer = CandidateNormalizer()
        safety_gate = SafetyGate()
        quality_gate = CandidateQualityGate()
        candidates: list[CandidateRecord] = []
        rejections: list[Rejection] = []

        for segment in segments:
            document = document_by_id.get(segment.source_id)
            if document is None:
                rejections.append(
                    Rejection(
                        item_id=segment.segment_id,
                        item_type="source_segment",
                        reasons=["missing_source_document"],
                    )
                )
                continue
            for extractor in extractors:
                raw_candidates: list[CandidateRecord]
                if isinstance(extractor, LLMCandidateExtractor):
                    llm_result = self._extract_llm_segment(
                        extractor,
                        segment,
                        document,
                        output_path=output_path,
                        recipe=recipe,
                        resume=resume,
                    )
                    raw_candidates = llm_result.candidates
                    rejections.extend(llm_result.rejections)
                else:
                    raw_candidates = extractor.extract(segment, document)
                for raw_candidate in raw_candidates:
                    normalized = normalizer.normalize(raw_candidate)
                    rejection = safety_gate.assess(normalized)
                    if rejection is not None:
                        rejections.append(rejection)
                        continue
                    quality_result = quality_gate.apply(normalized)
                    if isinstance(quality_result, Rejection):
                        rejections.append(quality_result)
                    else:
                        candidates.append(_attach_context_to_candidate(quality_result, segment))
        if any(isinstance(extractor, LLMCandidateExtractor) for extractor in extractors):
            _write_llm_progress(output_path, segments, recipe)
        return candidates, rejections

    def _extract_llm_segment(
        self,
        extractor: LLMCandidateExtractor,
        segment: SourceSegment,
        document: SourceDocument,
        *,
        output_path: Path,
        recipe: str,
        resume: bool,
    ) -> LLMExtractionResult:
        cache_path = _llm_segment_result_path(output_path, segment, recipe)
        if resume and cache_path.exists():
            return _read_llm_segment_result(cache_path)

        result = extractor.extract_with_rejections(segment, document)
        _write_llm_segment_result(cache_path, result)
        return result

    def _build_extractors(
        self, extractor_mode: str, llm_command: str | None, *, recipe: str
    ) -> list[object]:
        if extractor_mode == "deterministic":
            return [
                ProjectCapsuleExtractor(),
                ProcedureCandidateExtractor(),
                CodeOrConfigFactExtractor(),
            ]
        if extractor_mode == "llm":
            client = self.llm_client or (CommandLLMClient(llm_command) if llm_command else None)
            if client is None:
                raise ValueError("llm extractor requires an injected client or --llm-command")
            return [LLMCandidateExtractor(client, recipe=recipe)]
        if extractor_mode == "deterministic,llm":
            client = self.llm_client or (CommandLLMClient(llm_command) if llm_command else None)
            if client is None:
                raise ValueError(
                    "deterministic,llm extractor requires an injected client or --llm-command"
                )
            return [
                ProjectCapsuleExtractor(),
                ProcedureCandidateExtractor(),
                CodeOrConfigFactExtractor(),
                LLMCandidateExtractor(client, recipe=recipe),
            ]
        raise ValueError("unknown extractor mode")


def _normalize_context(context: dict[str, object] | ContextLabelSet | None) -> dict[str, object]:
    label_set = context if isinstance(context, ContextLabelSet) else context_from_mapping(context)
    mapping = context_to_mapping(label_set)
    return mapping if mapping["labels"] else {}


def _attach_context_to_documents(
    documents: list[SourceDocument], context: dict[str, object] | ContextLabelSet | None
) -> list[SourceDocument]:
    context_payload = _normalize_context(context)
    if not context_payload:
        return documents
    return [
        replace(document, metadata={**document.metadata, "context": context_payload})
        for document in documents
    ]


def _attach_context_to_segments(
    segments: list[SourceSegment], context: dict[str, object] | ContextLabelSet | None
) -> list[SourceSegment]:
    context_payload = _normalize_context(context)
    if not context_payload:
        return segments
    return [
        replace(segment, metadata={**segment.metadata, "context": context_payload})
        for segment in segments
    ]


def _attach_context_to_candidate(
    candidate: CandidateRecord, segment: SourceSegment
) -> CandidateRecord:
    context_payload = _normalize_context(segment.metadata)
    if not context_payload:
        return candidate
    return replace(candidate, ingestion={**candidate.ingestion, "context": context_payload})


def run_dry_inventory_and_segment(
    *,
    roots: Iterable[str | Path],
    output_dir: str | Path,
    recipe: str,
    run_id: str | None = None,
    created_at: str | None = None,
    include: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
    project: str | None = None,
    repo: str | None = None,
    collection: str | None = None,
    review_policy: str = "conservative",
    extractor_mode: str = "deterministic",
    llm_command: str | None = None,
    resume: bool = False,
    context: dict[str, object] | ContextLabelSet | None = None,
) -> PipelineResult:
    """Convenience wrapper for the default ingestion pipeline."""

    return IngestionPipeline().run_dry_inventory_and_segment(
        roots=roots,
        output_dir=output_dir,
        recipe=recipe,
        run_id=run_id,
        created_at=created_at,
        include=include,
        exclude=exclude,
        project=project,
        repo=repo,
        collection=collection,
        review_policy=review_policy,
        extractor_mode=extractor_mode,
        llm_command=llm_command,
        resume=resume,
        context=context,
    )


def _write_manifest(path: Path, manifest: IngestionRunManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _llm_segment_result_path(output_path: Path, segment: SourceSegment, recipe: str) -> Path:
    cache_key = stable_hash(
        {
            "recipe": recipe,
            "segment_id": segment.segment_id,
            "content_hash": segment.metadata.get("content_hash"),
        }
    )
    return output_path / "llm-segment-results" / f"{cache_key}.json"


def _write_llm_segment_result(path: Path, result: LLMExtractionResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "candidates": [candidate.to_dict() for candidate in result.candidates],
        "rejections": [rejection.to_dict() for rejection in result.rejections],
    }
    path.write_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _read_llm_segment_result(path: Path) -> LLMExtractionResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return LLMExtractionResult(
        candidates=[CandidateRecord.from_dict(row) for row in payload.get("candidates", [])],
        rejections=[Rejection.from_dict(row) for row in payload.get("rejections", [])],
    )


def _write_llm_progress(output_path: Path, segments: list[SourceSegment], recipe: str) -> None:
    done: list[dict[str, object]] = []
    todo: list[dict[str, object]] = []
    for segment in segments:
        row = {
            "segment_id": segment.segment_id,
            "source_id": segment.source_id,
            "title": segment.title,
            "content_hash": segment.metadata.get("content_hash"),
        }
        if _llm_segment_result_path(output_path, segment, recipe).exists():
            done.append(row)
        else:
            todo.append(row)
    write_jsonl(output_path / "segments.done.jsonl", done)
    write_jsonl(output_path / "segments.todo.jsonl", todo)


def _is_manpage_recipe(recipe: str) -> bool:
    return recipe in {"manpage", "openbsd-manpages"}


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
