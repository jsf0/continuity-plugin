from __future__ import annotations

import json
from pathlib import Path

from continuity.models import ContextRecord
from continuity.retrieval import ContinuityRetriever
from continuity.store import ContinuityStore

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "continuity_memory"


def load_records() -> list[ContextRecord]:
    return [
        ContextRecord.from_dict(json.loads(line))
        for line in (FIXTURE_DIR / "records.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]


def load_queries() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (FIXTURE_DIR / "queries.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]


def seeded_store(tmp_path: Path) -> ContinuityStore:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    for record in load_records():
        store.upsert_record(record)
    return store


def test_retriever_boosts_project_scoped_exact_matches(tmp_path: Path) -> None:
    retriever = ContinuityRetriever(seeded_store(tmp_path))

    hits = retriever.search("the subagent timed out without doing anything again", scope_project="guard-proxy", limit=3)

    assert hits[0].record.id == "r_delegate_timeout"
    assert hits[0].score > 0
    assert all(hit.record.id != "r_llama_systemd" for hit in hits)


def test_retriever_uses_tags_and_entities_for_non_fts_terms(tmp_path: Path) -> None:
    retriever = ContinuityRetriever(seeded_store(tmp_path))

    hits = retriever.search("api_calls:0 after 300s", scope_project="guard-proxy", limit=3)

    assert hits[0].record.id == "r_delegate_timeout"


def test_eval_fixture_queries_pass_phase2_retrieval(tmp_path: Path) -> None:
    retriever = ContinuityRetriever(seeded_store(tmp_path))

    for query in load_queries():
        hits = retriever.search(
            str(query["query"]),
            scope_project=query.get("scope_project"),
            limit=int(query["top_k"]),
        )
        hit_ids = [hit.record.id for hit in hits]

        for record_id in query.get("must_include", []):
            assert record_id in hit_ids, f"{record_id} missing for query {query['query']!r}"
        for record_id in query.get("must_not_include", []):
            assert record_id not in hit_ids, f"{record_id} unexpectedly returned for {query['query']!r}"
