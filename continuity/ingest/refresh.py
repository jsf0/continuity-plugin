"""Refresh and staleness detection for corpus ingestion runs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from continuity.ingest.connectors import LocalFilesConnector
from continuity.ingest.jsonl import read_jsonl, write_jsonl
from continuity.ingest.models import SourceDocument
from continuity.store import ContinuityStore

_PARSEABLE_SOURCE_TYPES = {"markdown", "rst", "text"}
_CORPUS_TRUST_LEVELS = {
    "corpus_distilled",
    "personal_note_distilled",
    "internet_distilled",
    "corpus_raw_summary",
    "candidate_unreviewed",
}


@dataclass(frozen=True)
class RefreshPlan:
    """Plan produced by comparing a previous inventory with a current scan."""

    previous_count: int
    current_count: int
    unchanged: list[SourceDocument] = field(default_factory=list)
    added: list[SourceDocument] = field(default_factory=list)
    changed: list[SourceDocument] = field(default_factory=list)
    removed: list[SourceDocument] = field(default_factory=list)
    stale_record_ids: list[str] = field(default_factory=list)
    archived_record_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_count": self.previous_count,
            "current_count": self.current_count,
            "unchanged_count": len(self.unchanged),
            "added_count": len(self.added),
            "changed_count": len(self.changed),
            "removed_count": len(self.removed),
            "stale_record_ids": self.stale_record_ids,
            "archived_record_ids": self.archived_record_ids,
        }


class RefreshPlanner:
    """Compare corpus inventories and optionally archive stale imported records."""

    def __init__(self, *, connector: LocalFilesConnector | None = None) -> None:
        self.connector = connector or LocalFilesConnector()

    def plan_from_inventory(
        self,
        *,
        previous_inventory_path: str | Path,
        current_documents: list[SourceDocument],
        store: ContinuityStore | None = None,
        apply: bool = False,
    ) -> RefreshPlan:
        previous_documents = [
            SourceDocument.from_dict(row) for row in read_jsonl(previous_inventory_path)
        ]
        return self.plan(
            previous_documents=previous_documents,
            current_documents=current_documents,
            store=store,
            apply=apply,
        )

    def discover_current(
        self,
        root: str | Path,
        *,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        project: str | None = None,
        repo: str | None = None,
        collection: str | None = None,
    ) -> list[SourceDocument]:
        return [
            document
            for document in self.connector.discover(
                root,
                include=include,
                exclude=exclude,
                project=project,
                repo=repo,
                collection=collection,
            )
            if document.source_type in _PARSEABLE_SOURCE_TYPES
        ]

    def plan(
        self,
        *,
        previous_documents: list[SourceDocument],
        current_documents: list[SourceDocument],
        store: ContinuityStore | None = None,
        apply: bool = False,
    ) -> RefreshPlan:
        previous_by_id = {document.source_id: document for document in previous_documents}
        current_by_id = {document.source_id: document for document in current_documents}

        unchanged: list[SourceDocument] = []
        changed: list[SourceDocument] = []
        added: list[SourceDocument] = []
        removed: list[SourceDocument] = []

        for source_id, current in current_by_id.items():
            previous = previous_by_id.get(source_id)
            if previous is None:
                added.append(current)
            elif _sha256(previous) == _sha256(current):
                unchanged.append(current)
            else:
                changed.append(current)

        for source_id, previous in previous_by_id.items():
            if source_id not in current_by_id:
                removed.append(previous)

        stale_uris = {document.uri for document in [*changed, *removed]}
        stale_record_ids = _stale_record_ids(store, stale_uris) if store is not None else []
        archived_record_ids: list[str] = []
        if store is not None and apply:
            store.migrate()
            for record_id in stale_record_ids:
                if store.archive_record(record_id, reason="corpus_source_changed_or_removed"):
                    archived_record_ids.append(record_id)

        return RefreshPlan(
            previous_count=len(previous_documents),
            current_count=len(current_documents),
            unchanged=sorted(unchanged, key=lambda document: document.source_id),
            added=sorted(added, key=lambda document: document.source_id),
            changed=sorted(changed, key=lambda document: document.source_id),
            removed=sorted(removed, key=lambda document: document.source_id),
            stale_record_ids=sorted(stale_record_ids),
            archived_record_ids=sorted(archived_record_ids),
        )


def write_refresh_artifacts(
    output_dir: str | Path,
    *,
    current_documents: list[SourceDocument],
    plan: RefreshPlan,
) -> None:
    """Write refresh comparison artifacts."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    write_jsonl(
        output_path / "current-inventory.jsonl",
        [document.to_dict() for document in current_documents],
    )
    write_jsonl(
        output_path / "added-sources.jsonl", [document.to_dict() for document in plan.added]
    )
    write_jsonl(
        output_path / "changed-sources.jsonl", [document.to_dict() for document in plan.changed]
    )
    write_jsonl(
        output_path / "removed-sources.jsonl", [document.to_dict() for document in plan.removed]
    )
    write_jsonl(
        output_path / "unchanged-sources.jsonl", [document.to_dict() for document in plan.unchanged]
    )
    (output_path / "refresh-report.json").write_text(
        json.dumps(plan.to_dict(), sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_path / "refresh-report.md").write_text(_render_markdown(plan), encoding="utf-8")


def _sha256(document: SourceDocument) -> str | None:
    value = document.metadata.get("sha256")
    return str(value) if value is not None else None


def _stale_record_ids(store: ContinuityStore | None, stale_uris: set[str]) -> list[str]:
    if store is None or not stale_uris:
        return []
    store.migrate()
    record_ids: list[str] = []
    for record in store.list_records():
        if record.status != "active" or record.trust_level not in _CORPUS_TRUST_LEVELS:
            continue
        if any(source.uri in stale_uris for source in record.sources):
            record_ids.append(record.id)
    return record_ids


def _render_markdown(plan: RefreshPlan) -> str:
    lines = [
        "# Ingestion Refresh Report",
        "",
        "## Summary",
        "",
        f"Previous sources: {plan.previous_count}",
        f"Current sources: {plan.current_count}",
        f"Unchanged sources: {len(plan.unchanged)}",
        f"Added sources: {len(plan.added)}",
        f"Changed sources: {len(plan.changed)}",
        f"Removed sources: {len(plan.removed)}",
        f"Stale continuity records: {len(plan.stale_record_ids)}",
        f"Archived continuity records: {len(plan.archived_record_ids)}",
        "",
    ]
    for title, documents in [
        ("Added", plan.added),
        ("Changed", plan.changed),
        ("Removed", plan.removed),
    ]:
        if documents:
            lines.extend([f"## {title}", ""])
            lines.extend(f"- `{document.source_id}`" for document in documents)
            lines.append("")
    if plan.stale_record_ids:
        lines.extend(["## Stale Records", ""])
        lines.extend(f"- `{record_id}`" for record_id in plan.stale_record_ids)
        lines.append("")
    return "\n".join(lines)
