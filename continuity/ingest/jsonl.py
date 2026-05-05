"""JSONL helpers for ingestion artifacts."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]


def read_jsonl(path: str | Path) -> list[JsonObject]:
    """Read a JSONL file containing one JSON object per nonblank line."""

    jsonl_path = Path(path)
    rows: list[JsonObject] = []
    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JSONL in {jsonl_path} on line {line_number}: {exc}"
                ) from exc
            if not isinstance(value, dict):
                raise TypeError(
                    f"JSONL rows must be objects; line {line_number} is {type(value).__name__}"
                )
            rows.append(value)
    return rows


def write_jsonl(path: str | Path, rows: Iterable[JsonObject]) -> None:
    """Write JSON object rows to a JSONL file, replacing existing content."""

    jsonl_path = Path(path)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("JSONL rows must be objects")
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
