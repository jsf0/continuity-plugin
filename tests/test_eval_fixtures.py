from __future__ import annotations

import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "continuity_memory"


def load_jsonl(name: str) -> list[dict[str, object]]:
    path = FIXTURE_DIR / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_record_fixtures_have_required_phase0_fields() -> None:
    records = load_jsonl("records.jsonl")

    assert records, "Phase 0 must include seed records for retrieval evaluation"
    for record in records:
        assert isinstance(record.get("id"), str) and record["id"]
        assert isinstance(record.get("kind"), str) and record["kind"]
        assert isinstance(record.get("title"), str) and record["title"]
        assert isinstance(record.get("summary"), str) and record["summary"]
        assert isinstance(record.get("tags"), list)
        assert isinstance(record.get("entities"), list)
        assert 0 <= float(record.get("confidence", -1)) <= 1
        assert 0 <= float(record.get("importance", -1)) <= 1


def test_query_fixtures_reference_existing_records() -> None:
    records = load_jsonl("records.jsonl")
    queries = load_jsonl("queries.jsonl")
    record_ids = {record["id"] for record in records}

    assert queries, "Phase 0 must include retrieval eval queries"
    for query in queries:
        assert isinstance(query.get("query"), str) and query["query"]
        assert int(query.get("top_k", 0)) > 0
        for record_id in query.get("must_include", []):
            assert record_id in record_ids
        for record_id in query.get("must_not_include", []):
            assert record_id in record_ids


def test_session_fixtures_are_valid_message_lists() -> None:
    sessions = load_jsonl("sessions.jsonl")

    assert sessions, "Phase 0 must include session fixtures for future consolidation tests"
    for session in sessions:
        assert isinstance(session.get("id"), str) and session["id"]
        messages = session.get("messages")
        assert isinstance(messages, list)
        for message in messages:
            assert message["role"] in {"user", "assistant", "tool", "system"}
            assert isinstance(message["content"], str)
