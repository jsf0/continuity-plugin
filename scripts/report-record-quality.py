#!/usr/bin/env python
"""Report or backfill quality metadata for an existing continuity SQLite DB."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from continuity.quality_backfill import apply_quality_backfill, build_quality_backfill_report
from continuity.store import ContinuityStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to continuity.db")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Only inspect active records; default includes archived/retracted records for audit.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Persist recomputed quality_json for records whose quality metadata differs. "
            "Dry-run/report-only is the default."
        ),
    )
    args = parser.parse_args()

    store = ContinuityStore(Path(args.db))
    store.migrate()
    if args.apply:
        report = apply_quality_backfill(
            store,
            limit=args.limit,
            active_only=args.active_only,
        )
    else:
        report = build_quality_backfill_report(
            store,
            limit=args.limit,
            active_only=args.active_only,
        )
    payload = report.to_dict()
    payload["dry_run"] = not args.apply
    payload["active_only"] = args.active_only
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
