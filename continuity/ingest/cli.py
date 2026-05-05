"""Command-line interface for corpus ingestion."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from continuity.ingest.eval import EvalRunner
from continuity.ingest.importer import ContinuityImporter
from continuity.ingest.jsonl import read_jsonl, write_jsonl
from continuity.ingest.models import CandidateRecord, SourceDocument, SourceSegment
from continuity.ingest.parsers import parser_for_document
from continuity.ingest.pipeline import IngestionPipeline
from continuity.ingest.review import ReviewPolicy, write_review_artifacts
from continuity.ingest.segmenters import HeadingSectionSegmenter
from continuity.store import ContinuityStore


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ingestion CLI and return a process-style exit code."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="continuity-ingest")
    subcommands = parser.add_subparsers(dest="command", required=True)

    inventory = subcommands.add_parser("inventory", help="Discover local source documents")
    inventory.add_argument("path")
    _add_include_exclude(inventory)
    inventory.add_argument("--project")
    inventory.add_argument("--repo")
    inventory.add_argument("--collection")
    inventory.add_argument("--output", required=True)
    inventory.set_defaults(func=_cmd_inventory)

    segment = subcommands.add_parser("segment", help="Parse and segment an inventory JSONL file")
    segment.add_argument("inventory")
    segment.add_argument("--output", required=True)
    segment.set_defaults(func=_cmd_segment)

    run = subcommands.add_parser("run", help="Run dry inventory and segmentation pipeline")
    run.add_argument("path")
    run.add_argument("--recipe", default="docs")
    run.add_argument("--run-id")
    run.add_argument("--created-at")
    _add_include_exclude(run)
    run.add_argument("--project")
    run.add_argument("--repo")
    run.add_argument("--collection")
    run.add_argument("--policy", default="conservative")
    run.add_argument("--output", required=True)
    run.set_defaults(func=_cmd_run)

    review = subcommands.add_parser("review", help="Review candidate records")
    review.add_argument("candidates")
    review.add_argument("--policy", default="conservative")
    review.add_argument("--output-dir", required=True)
    review.set_defaults(func=_cmd_review)

    import_cmd = subcommands.add_parser("import", help="Import approved candidate records")
    import_cmd.add_argument("approved_records")
    import_cmd.add_argument(
        "--db-path", default=str(Path.home() / ".hermes" / "continuity" / "memory.db")
    )
    import_cmd.add_argument("--apply", action="store_true")
    import_cmd.set_defaults(func=_cmd_import)

    eval_cmd = subcommands.add_parser("eval", help="Run retrieval eval cases")
    eval_cmd.add_argument("evals")
    eval_cmd.add_argument(
        "--db-path", default=str(Path.home() / ".hermes" / "continuity" / "memory.db")
    )
    eval_cmd.add_argument("--report")
    eval_cmd.set_defaults(func=_cmd_eval)

    return parser


def _add_include_exclude(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--include", action="append")
    parser.add_argument("--exclude", action="append")


def _cmd_inventory(args: argparse.Namespace) -> None:
    result = IngestionPipeline().connector.discover(
        args.path,
        include=args.include,
        exclude=args.exclude,
        project=args.project,
        repo=args.repo,
        collection=args.collection,
    )
    documents = [document.to_dict() for document in result if document.source_type != "binary"]
    write_jsonl(args.output, documents)


def _cmd_segment(args: argparse.Namespace) -> None:
    documents = [SourceDocument.from_dict(row) for row in read_jsonl(args.inventory)]
    segments: list[SourceSegment] = []
    segmenter = HeadingSectionSegmenter()
    for document in documents:
        parsed = parser_for_document(document).parse(document)
        segments.extend(segmenter.segment(parsed, document))
    write_jsonl(args.output, [segment.to_dict() for segment in segments])


def _cmd_run(args: argparse.Namespace) -> None:
    IngestionPipeline().run_dry_inventory_and_segment(
        roots=[args.path],
        output_dir=args.output,
        recipe=args.recipe,
        run_id=args.run_id,
        created_at=args.created_at,
        include=args.include,
        exclude=args.exclude,
        project=args.project,
        repo=args.repo,
        collection=args.collection,
        review_policy=args.policy,
    )


def _cmd_review(args: argparse.Namespace) -> None:
    candidates = [CandidateRecord.from_dict(row) for row in read_jsonl(args.candidates)]
    write_review_artifacts(
        args.output_dir,
        candidates=candidates,
        rejections=[],
        policy=ReviewPolicy(args.policy),
    )


def _cmd_import(args: argparse.Namespace) -> None:
    candidates = [CandidateRecord.from_dict(row) for row in read_jsonl(args.approved_records)]
    result = ContinuityImporter(ContinuityStore(args.db_path)).import_records(
        candidates,
        dry_run=not args.apply,
    )
    print(json.dumps(result.__dict__, sort_keys=True))


def _cmd_eval(args: argparse.Namespace) -> None:
    result = EvalRunner(ContinuityStore(args.db_path)).run_file(args.evals, report_path=args.report)
    print(
        json.dumps(
            {
                "passed": result.passed,
                "total": result.total,
                "passed_count": result.passed_count,
                "failed_count": result.failed_count,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
