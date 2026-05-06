#!/usr/bin/env python
"""Report write-time quality warnings for an existing continuity SQLite DB."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from continuity.record_quality import enrich_record_metadata
from continuity.store import ContinuityStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to continuity.db")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    store = ContinuityStore(Path(args.db))
    store.migrate()
    records = store.list_records()
    report_records: list[dict[str, object]] = []
    warnings: Counter[str] = Counter()
    review_required = 0
    for record in records:
        enriched, assessment = enrich_record_metadata(record)
        quality = record.quality or enriched.quality or assessment.to_dict()
        record_warnings = list(quality.get("warnings", [])) if isinstance(quality, dict) else []
        if not record_warnings and assessment.warnings:
            record_warnings = list(assessment.warnings)
        is_review_required = (
            bool(quality.get("review_required")) if isinstance(quality, dict) else False
        )
        is_review_required = is_review_required or assessment.review_required
        if record_warnings or is_review_required:
            warnings.update(record_warnings)
            review_required += int(is_review_required)
            report_records.append(
                {
                    "id": record.id,
                    "kind": record.kind,
                    "title": record.title,
                    "status": record.status,
                    "trust_level": record.trust_level,
                    "warnings": record_warnings,
                    "review_required": is_review_required,
                    "score": quality.get("score", assessment.score)
                    if isinstance(quality, dict)
                    else assessment.score,
                }
            )
    report_records.sort(key=lambda item: (float(item.get("score", 1.0)), str(item["id"])))
    payload = {
        "record_count": len(records),
        "warning_count": len(report_records),
        "review_required_count": review_required,
        "top_warnings": warnings.most_common(),
        "records": report_records[: max(1, args.limit)],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
