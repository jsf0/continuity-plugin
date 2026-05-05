from __future__ import annotations

import pytest

from continuity.ingest.jsonl import read_jsonl, write_jsonl


def test_write_and_read_jsonl_round_trip(tmp_path) -> None:
    path = tmp_path / "records.jsonl"
    rows = [
        {"id": "one", "tags": ["a", "b"]},
        {"id": "two", "nested": {"value": 2}},
    ]

    write_jsonl(path, rows)

    assert read_jsonl(path) == rows
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_read_jsonl_skips_blank_lines(tmp_path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text('{"id":"one"}\n\n{"id":"two"}\n', encoding="utf-8")

    assert read_jsonl(path) == [{"id": "one"}, {"id": "two"}]


def test_read_jsonl_reports_line_number_for_invalid_json(tmp_path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text('{"id":"one"}\nnot-json\n', encoding="utf-8")

    with pytest.raises(ValueError, match="line 2"):
        read_jsonl(path)


def test_write_jsonl_rejects_non_object_rows(tmp_path) -> None:
    path = tmp_path / "records.jsonl"

    with pytest.raises(TypeError, match="JSONL rows must be objects"):
        write_jsonl(path, [{"ok": True}, ["not", "an", "object"]])
