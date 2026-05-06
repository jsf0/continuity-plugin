#!/usr/bin/env python3
"""Show a small-model prompt before and after continuity memory injection.

This is a deterministic, synthetic demo. It does not call an LLM or read the
user's real memory database. Instead, it loads the public demo corpus into a
temporary HERMES_HOME and prints the compact context block a small model would
receive for the same question.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO_RECORDS = ROOT / "examples" / "demo_memory" / "records.jsonl"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from continuity import ContinuityProvider  # noqa: E402
from continuity.models import ContextRecord  # noqa: E402

QUERY = "What API framework should demo-dashboard use?"
EXPECTED_ANSWER = "FastAPI"


def main() -> int:
    records = load_records(DEMO_RECORDS)
    with tempfile.TemporaryDirectory(prefix="continuity-small-model-demo-") as temp_dir:
        provider = ContinuityProvider()
        provider.initialize(
            session_id="demo-small-model-context",
            hermes_home=temp_dir,
            continuity_config={
                "max_records": 1,
                "max_chars": 900,
                "include_sources": False,
                "include_scores": True,
                "vector": {"enabled": True, "backend": "sqlite-hash"},
                "association_graph": {"enabled": True},
                "dream": {"enabled": False},
            },
        )
        seed_provider(provider, records)
        context = provider.prefetch(QUERY, scope_project="demo-dashboard")
        if EXPECTED_ANSWER not in context:
            print(
                "small model context demo failed: expected context did not mention FastAPI",
                file=sys.stderr,
            )
            return 1
        retrieved_records = sum(
            1 for line in context.splitlines() if line.lstrip().startswith(tuple("123456789"))
        )
        if retrieved_records != 1:
            print(
                f"small model context demo failed: expected 1 retrieved record, got {retrieved_records}",
                file=sys.stderr,
            )
            return 1

        print("Small-model continuity context demo")
        print(f"question={QUERY!r}")
        print()
        print("WITHOUT continuity")
        print("prompt_context_chars=0")
        print("expected_small_model_behavior=ask the user or guess; no project memory is present")
        print()
        print("WITH continuity")
        print(f"prompt_context_chars={len(context)}")
        print(f"retrieved_records={retrieved_records}")
        print(context)
        print()
        print(f"expected_answer={EXPECTED_ANSWER}")
        print("small model context demo ok")
    return 0


def load_records(path: Path) -> list[ContextRecord]:
    return [
        ContextRecord.from_dict(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def seed_provider(provider: ContinuityProvider, records: list[ContextRecord]) -> None:
    if provider._store is None:
        raise RuntimeError("provider store was not initialized")
    for record in records:
        provider._store.upsert_record(record)
        if provider._vector_backend is not None:
            provider._vector_backend.upsert(record.id, record.embedding_text or "")


if __name__ == "__main__":
    raise SystemExit(main())
