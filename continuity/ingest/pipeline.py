"""Dry-run ingestion pipeline orchestration."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from continuity.ingest.connectors import LocalFilesConnector
from continuity.ingest.jsonl import write_jsonl
from continuity.ingest.models import (
    IngestionRunManifest,
    SourceDocument,
    SourceSegment,
    stable_hash,
)
from continuity.ingest.parsers import parser_for_document
from continuity.ingest.reports import render_dry_run_report
from continuity.ingest.segmenters import HeadingSectionSegmenter

_PARSEABLE_SOURCE_TYPES = {"markdown", "rst", "text"}


@dataclass(frozen=True)
class PipelineResult:
    """Artifacts produced by a dry-run ingestion pipeline."""

    output_dir: Path
    manifest: IngestionRunManifest
    documents: list[SourceDocument]
    segments: list[SourceSegment]


class IngestionPipeline:
    """Coordinate source discovery, parsing, segmentation, and artifact writing."""

    def __init__(self, *, connector: LocalFilesConnector | None = None) -> None:
        self.connector = connector or LocalFilesConnector()

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
    ) -> PipelineResult:
        """Run the dry inventory/parse/segment phase and write JSONL artifacts."""

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
            }
        )

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

        segments: list[SourceSegment] = []
        segmenter = HeadingSectionSegmenter()
        for document in documents:
            parsed = parser_for_document(document).parse(document)
            segments.extend(segmenter.segment(parsed, document))

        manifest = IngestionRunManifest(
            run_id=effective_run_id,
            created_at=timestamp,
            recipe=recipe,
            input_roots=[str(root) for root in root_paths],
            config_hash=config_hash,
            source_count=len(documents),
            segment_count=len(segments),
            candidate_count=0,
            approved_count=0,
            imported_count=0,
            rejected_count=0,
            output_dir=str(output_path),
        )

        _write_manifest(output_path / "manifest.json", manifest)
        write_jsonl(output_path / "inventory.jsonl", [document.to_dict() for document in documents])
        write_jsonl(output_path / "segments.jsonl", [segment.to_dict() for segment in segments])
        (output_path / "import-report.md").write_text(
            render_dry_run_report(manifest), encoding="utf-8"
        )

        return PipelineResult(
            output_dir=output_path,
            manifest=manifest,
            documents=documents,
            segments=segments,
        )


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
    )


def _write_manifest(path: Path, manifest: IngestionRunManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
