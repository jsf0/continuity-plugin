"""Markdown reports for ingestion runs."""

from __future__ import annotations

from continuity.ingest.models import IngestionRunManifest


def render_dry_run_report(manifest: IngestionRunManifest) -> str:
    """Render a compact human-readable dry-run report."""

    return "\n".join(
        [
            "# Ingestion Dry Run Report",
            "",
            f"Run ID: {manifest.run_id}",
            f"Recipe: {manifest.recipe}",
            f"Created at: {manifest.created_at}",
            "",
            "## Summary",
            "",
            f"Sources discovered: {manifest.source_count}",
            f"Segments generated: {manifest.segment_count}",
            f"Candidate records: {manifest.candidate_count}",
            f"Approved records: {manifest.approved_count}",
            f"Imported records: {manifest.imported_count}",
            f"Rejected items: {manifest.rejected_count}",
            "",
            "No candidate extraction or import was performed in this dry-run stage.",
            "",
        ]
    )
