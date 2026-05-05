#!/usr/bin/env python3
"""Run a public continuity-memory retrieval demo against a temporary DB.

The demo loads synthetic records from examples/demo_memory, runs retrieval
expectations, exercises add/search/archive/restore/delete, and runs a report-only
dream cycle. It never reads or writes the user's real continuity database.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "examples" / "demo_memory"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from continuity import ContinuityProvider  # noqa: E402
from continuity.models import ContextRecord  # noqa: E402


@dataclass(frozen=True)
class QueryExpectation:
    name: str
    query: str
    scope_project: str | None
    top_k: int
    must_include: tuple[str, ...]
    must_not_include: tuple[str, ...]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo-dir",
        type=Path,
        default=DEMO_DIR,
        help="Directory containing records.jsonl and queries.jsonl.",
    )
    parser.add_argument("--quiet", action="store_true", help="Print only final status.")
    args = parser.parse_args()

    try:
        run_demo(args.demo_dir, quiet=args.quiet)
    except DemoError as exc:
        print(f"demo retrieval failed: {exc}", file=sys.stderr)
        return 1
    print("demo retrieval ok")
    return 0


class DemoError(RuntimeError):
    """Raised when the demo does not meet its expected retrieval behavior."""


def run_demo(demo_dir: Path, *, quiet: bool = False) -> None:
    records = load_records(demo_dir / "records.jsonl")
    queries = load_queries(demo_dir / "queries.jsonl")

    with tempfile.TemporaryDirectory(prefix="continuity-demo-") as temp_dir:
        provider = ContinuityProvider()
        provider.initialize(
            session_id="demo-retrieval",
            hermes_home=temp_dir,
            continuity_config={
                "max_records": 5,
                "max_chars": 1800,
                "vector": {"enabled": True, "backend": "sqlite-hash"},
                "association_graph": {"enabled": True},
                "dream": {"enabled": False},
            },
        )
        seed_provider(provider, records)

        if not quiet:
            print("Continuity demo retrieval")
            print(f"  fixture records: {len(records)}")
            print(f"  fixture queries: {len(queries)}")
            print(f"  temporary home: {temp_dir}")
            print()

        run_query_expectations(provider, queries, quiet=quiet)
        run_round_trip_checks(provider, quiet=quiet)
        run_dream_report_check(provider, quiet=quiet)


def load_records(path: Path) -> list[ContextRecord]:
    return [
        ContextRecord.from_dict(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_queries(path: Path) -> list[QueryExpectation]:
    queries: list[QueryExpectation] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        queries.append(
            QueryExpectation(
                name=str(value["name"]),
                query=str(value["query"]),
                scope_project=_optional_str(value.get("scope_project")),
                top_k=int(value.get("top_k", 3)),
                must_include=tuple(str(item) for item in value.get("must_include", [])),
                must_not_include=tuple(str(item) for item in value.get("must_not_include", [])),
            )
        )
    return queries


def seed_provider(provider: ContinuityProvider, records: list[ContextRecord]) -> None:
    store = provider._store
    vector_backend = provider._vector_backend
    if store is None:
        raise DemoError("provider store was not initialized")
    for record in records:
        store.upsert_record(record)
        if vector_backend:
            vector_backend.upsert(record.id, record.embedding_text or "")


def run_query_expectations(
    provider: ContinuityProvider, queries: list[QueryExpectation], *, quiet: bool
) -> None:
    if not quiet:
        print("Query checks")
    for expected in queries:
        payload = call_json(
            provider,
            "continuity_search",
            {
                "query": expected.query,
                "scope_project": expected.scope_project,
                "limit": expected.top_k,
            },
        )
        results = payload.get("results", [])
        hit_ids = [str(result["id"]) for result in results]
        missing = [record_id for record_id in expected.must_include if record_id not in hit_ids]
        unexpected = [record_id for record_id in expected.must_not_include if record_id in hit_ids]
        if missing or unexpected:
            raise DemoError(
                f"query {expected.name!r} failed: missing={missing}, "
                f"unexpected={unexpected}, hits={hit_ids}"
            )
        if not quiet:
            print(f"  ✓ {expected.name}: {', '.join(hit_ids) or '(no hits)'}")
    if not quiet:
        print()


def run_round_trip_checks(provider: ContinuityProvider, *, quiet: bool) -> None:
    if not quiet:
        print("Round-trip checks")
    record_id = "r_demo_runtime_roundtrip"
    add_payload = call_json(
        provider,
        "continuity_add",
        {
            "id": record_id,
            "kind": "lesson_learned",
            "title": "Runtime demo round-trip record",
            "summary": "Runtime demo record proves add, search, archive, restore, and delete round-trip behavior.",
            "scope_project": "demo-runtime",
            "tags": ["runtime-demo", "roundtrip"],
            "entities": ["round-trip retrieval"],
            "confidence": 0.9,
            "importance": 0.75,
        },
    )
    require_success(add_payload, "add runtime record")

    assert_search_contains(
        provider, "runtime demo roundtrip", record_id, scope_project="demo-runtime"
    )
    require_success(
        call_json(provider, "continuity_archive", {"id": record_id, "reason": "demo archive"}),
        "archive runtime record",
    )
    assert_search_not_contains(
        provider, "runtime demo roundtrip", record_id, scope_project="demo-runtime"
    )
    require_success(
        call_json(provider, "continuity_restore", {"id": record_id}), "restore runtime record"
    )
    assert_search_contains(
        provider, "runtime demo roundtrip", record_id, scope_project="demo-runtime"
    )
    require_success(
        call_json(provider, "continuity_delete", {"id": record_id}), "delete runtime record"
    )
    missing = call_json(provider, "continuity_get", {"id": record_id})
    if missing.get("success") is not False:
        raise DemoError("deleted runtime record was still fetchable")
    if not quiet:
        print("  ✓ add/search/archive/restore/delete")
        print()


def run_dream_report_check(provider: ContinuityProvider, *, quiet: bool) -> None:
    if not quiet:
        print("Dream/prune report")
    payload = call_json(provider, "continuity_dream", {"mode": "report", "limit": 5})
    require_success(payload, "dream report")
    candidates = payload.get("stale_candidates", [])
    candidate_ids = {
        str(candidate.get("id")) for candidate in candidates if isinstance(candidate, dict)
    }
    if "r_demo_project_state_old" not in candidate_ids:
        raise DemoError(f"dream report did not flag old project state: {candidates}")
    if payload.get("archived_ids") or payload.get("deleted_ids"):
        raise DemoError("report-only dream mutated records")
    if not quiet:
        print("  ✓ report-only dream flags superseded project state")
        print()


def assert_search_contains(
    provider: ContinuityProvider, query: str, record_id: str, *, scope_project: str | None = None
) -> None:
    payload = call_json(
        provider,
        "continuity_search",
        {"query": query, "scope_project": scope_project, "limit": 5},
    )
    hit_ids = [str(result["id"]) for result in payload.get("results", [])]
    if record_id not in hit_ids:
        raise DemoError(f"expected {record_id} in search hits for {query!r}, got {hit_ids}")


def assert_search_not_contains(
    provider: ContinuityProvider, query: str, record_id: str, *, scope_project: str | None = None
) -> None:
    payload = call_json(
        provider,
        "continuity_search",
        {"query": query, "scope_project": scope_project, "limit": 5},
    )
    hit_ids = [str(result["id"]) for result in payload.get("results", [])]
    if record_id in hit_ids:
        raise DemoError(f"did not expect {record_id} in search hits for {query!r}")


def call_json(provider: ContinuityProvider, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    return json.loads(provider.handle_tool_call(tool_name, args))


def require_success(payload: dict[str, Any], action: str) -> None:
    if payload.get("success") is not True:
        raise DemoError(f"{action} failed: {payload}")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


if __name__ == "__main__":
    raise SystemExit(main())
