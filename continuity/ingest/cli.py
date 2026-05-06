"""Command-line interface for corpus ingestion."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from continuity.context_labels import context_from_mapping, context_to_mapping
from continuity.ingest.eval import EvalRunner
from continuity.ingest.importer import ContinuityImporter
from continuity.ingest.jsonl import read_jsonl, write_jsonl
from continuity.ingest.models import CandidateRecord, SourceDocument, SourceSegment
from continuity.ingest.parsers import parser_for_document
from continuity.ingest.pipeline import IngestionPipeline
from continuity.ingest.refresh import RefreshPlanner, write_refresh_artifacts
from continuity.ingest.review import ReviewPolicy, write_review_artifacts
from continuity.ingest.segmenters import HeadingSectionSegmenter
from continuity.store import ContinuityStore


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ingestion CLI and return a process-style exit code."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    result = args.func(args)
    return int(result or 0)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="continuity-ingest")
    subcommands = parser.add_subparsers(dest="command", required=True)

    inventory = subcommands.add_parser("inventory", help="Discover local source documents")
    inventory.add_argument("path")
    _add_include_exclude(inventory)
    _add_context_args(inventory)
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
    _add_context_args(run)
    run.add_argument("--project")
    run.add_argument("--repo")
    run.add_argument("--collection")
    run.add_argument("--policy", default="conservative")
    run.add_argument(
        "--extractor",
        choices=["deterministic", "llm", "deterministic,llm"],
        default="deterministic",
    )
    run.add_argument("--llm-command")
    run.add_argument("--resume", action="store_true")
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

    validate_import = subcommands.add_parser(
        "validate-import",
        help="Import approved records into a temporary DB and run retrieval evals",
    )
    validate_import.add_argument("approved_records")
    validate_import.add_argument("--evals", required=True)
    validate_import.add_argument("--report")
    validate_import.set_defaults(func=_cmd_validate_import)

    refresh = subcommands.add_parser(
        "refresh", help="Compare a corpus scan with a previous inventory"
    )
    refresh.add_argument("path")
    refresh.add_argument("--previous-inventory", required=True)
    _add_include_exclude(refresh)
    _add_context_args(refresh)
    refresh.add_argument("--project")
    refresh.add_argument("--repo")
    refresh.add_argument("--collection")
    refresh.add_argument("--db-path")
    refresh.add_argument("--apply", action="store_true")
    refresh.add_argument("--output", required=True)
    refresh.set_defaults(func=_cmd_refresh)

    return parser


def _add_include_exclude(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--include", action="append")
    parser.add_argument("--exclude", action="append")


def _add_context_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--context", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--partition-key", action="append", default=[])
    parser.add_argument("--soft-key", action="append", default=[])
    parser.add_argument("--identity-key", action="append", default=[])
    parser.add_argument("--collision-risk", choices=["normal", "high"], default="normal")


def _parse_context_args(args: argparse.Namespace) -> dict[str, object]:
    labels: dict[str, str] = {}
    for item in getattr(args, "context", []) or []:
        if "=" not in item:
            raise SystemExit(f"--context must be KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        labels[key] = value
    raw_context = {
        "labels": labels,
        "partition_keys": getattr(args, "partition_key", []) or [],
        "soft_keys": getattr(args, "soft_key", []) or [],
        "identity_keys": getattr(args, "identity_key", []) or [],
        "collision_risk": getattr(args, "collision_risk", "normal"),
    }
    label_set = context_from_mapping(raw_context)
    if labels and len(label_set.labels) != len(labels):
        raise SystemExit("invalid --context label: keys and values must be non-empty safe atoms")
    invalid_policy_keys = sorted(
        set(raw_context["partition_keys"])
        | set(raw_context["soft_keys"])
        | set(raw_context["identity_keys"]) - set(label_set.labels)
    )
    if labels and invalid_policy_keys:
        raise SystemExit(
            "invalid context policy key(s): "
            + ", ".join(str(key) for key in invalid_policy_keys)
            + " must match a --context key"
        )
    return context_to_mapping(label_set)


def _cmd_inventory(args: argparse.Namespace) -> None:
    result = IngestionPipeline().connector.discover(
        args.path,
        include=args.include,
        exclude=args.exclude,
        project=args.project,
        repo=args.repo,
        collection=args.collection,
    )
    context = _parse_context_args(args)
    documents = []
    for document in result:
        if document.source_type == "binary":
            continue
        row = document.to_dict()
        if context["labels"]:
            row["metadata"] = {**row.get("metadata", {}), "context": context}
        documents.append(row)
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
        extractor_mode=args.extractor,
        llm_command=args.llm_command,
        resume=args.resume,
        context=_parse_context_args(args),
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


def _cmd_validate_import(args: argparse.Namespace) -> int:
    candidates = [CandidateRecord.from_dict(row) for row in read_jsonl(args.approved_records)]
    with TemporaryDirectory(prefix="continuity-ingest-validate-") as temp_dir:
        db_path = Path(temp_dir) / "continuity.db"
        store = ContinuityStore(db_path)
        import_result = ContinuityImporter(store).import_records(candidates, dry_run=False)
        eval_result = EvalRunner(store).run_file(args.evals, report_path=args.report)
    print(
        json.dumps(
            {
                "passed": eval_result.passed,
                "total": eval_result.total,
                "passed_count": eval_result.passed_count,
                "failed_count": eval_result.failed_count,
                "import_created": len(import_result.created),
                "import_updated": len(import_result.updated),
                "import_failed": len(import_result.failed),
                "temporary_db": True,
            },
            sort_keys=True,
        )
    )
    return 0 if eval_result.passed and not import_result.failed else 1


def _cmd_refresh(args: argparse.Namespace) -> None:
    planner = RefreshPlanner()
    current_documents = planner.discover_current(
        args.path,
        include=args.include,
        exclude=args.exclude,
        project=args.project,
        repo=args.repo,
        collection=args.collection,
    )
    context = _parse_context_args(args)
    if context["labels"]:
        from dataclasses import replace

        current_documents = [
            replace(document, metadata={**document.metadata, "context": context})
            for document in current_documents
        ]
    store = ContinuityStore(args.db_path) if args.db_path else None
    plan = planner.plan_from_inventory(
        previous_inventory_path=args.previous_inventory,
        current_documents=current_documents,
        store=store,
        apply=args.apply,
    )
    write_refresh_artifacts(args.output, current_documents=current_documents, plan=plan)
    print(json.dumps(plan.to_dict(), sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
