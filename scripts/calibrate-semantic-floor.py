#!/usr/bin/env python3
"""Calibrate the semantic-candidate floor (semantic_candidates.min_similarity).

Run after switching embedding models or after significant corpus growth:

    uv run python scripts/calibrate-semantic-floor.py [--db PATH] [--model ID]

Methodology (IMPORTANT — measures VECTOR-ONLY candidates, not all top hits;
the tier only sees records with no FTS/tag/entity/text anchor, which score
lower than anchored hits):

1. For each probe query, embed the query, fetch the top vector hit that has
   no lexical anchor against the query tokens, and record its raw cosine.
2. ON-DOMAIN queries are ones whose true answer lives in the corpus (edit
   the lists below to match YOUR corpus). OFF-DOMAIN queries have no answer
   in the corpus.
3. Set min_similarity between the highest off-domain score and the lowest
   on-domain score of the records you actually want offered. Borderline
   off-domain cases that pass the floor are accepted noise: the consuming
   model dismisses them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from continuity.embeddings import SentenceTransformersVectorBackend
from continuity.retrieval import (
    _is_inactive_or_expired,
    _query_tokens,
    _record_text_tokens,
)
from continuity.store import ContinuityStore

# Edit these to match your corpus: on-domain queries must have a true answer
# stored; off-domain queries must not.
ON_DOMAIN = [
    "what maintenance do I need for my car",
    "what car do I drive",
    "how do I encrypt my backups",
    "when does the weekly archive job run",
    "what oil should I use",
    "am I happy in my current job",
]
OFF_DOMAIN = [
    "what is the capital of France",
    "explain photosynthesis to a ten year old",
    "how tall is Mount Everest",
    "who wrote Hamlet",
    "what is the boiling point of water at sea level",
    "what causes the northern lights",
]


def top_vector_only(embed: object, store: ContinuityStore, query: str) -> tuple[float, str] | None:
    hits = embed.search(query, limit=10)
    tokens = _query_tokens(query)
    by_id = {r.id: r for r in store.list_records() if not _is_inactive_or_expired(r)}
    for hit in hits:
        record = by_id[hit.record_id]
        # lexical anchor check, mirroring _candidate_has_lexical_anchor:
        if tokens & _record_text_tokens(record):
            continue  # anchored records are not tier candidates
        return hit.score, record.title
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(Path.home() / ".hermes/continuity/continuity.db"))
    parser.add_argument("--model", default="mixedbread-ai/mxbai-embed-large-v1")
    args = parser.parse_args()

    store = ContinuityStore(args.db)
    embed = SentenceTransformersVectorBackend(store, model=args.model)

    on: list[float] = []
    print("ON-DOMAIN (true answer in corpus) — top VECTOR-ONLY match:")
    for q in ON_DOMAIN:
        got = top_vector_only(embed, store, q)
        if got is None:
            print(f"  (none)  {q}")
            continue
        on.append(got[0])
        print(f"  {got[0]:.3f}  {q[:48]:50s} -> {got[1][:40]}")

    off: list[float] = []
    print("OFF-DOMAIN (nothing answers) — top VECTOR-ONLY match:")
    for q in OFF_DOMAIN:
        got = top_vector_only(embed, store, q)
        if got is None:
            print(f"  (none)  {q}")
            continue
        off.append(got[0])
        print(f"  {got[0]:.3f}  {q[:48]:50s} -> {got[1][:40]}")

    print()
    if on and off:
        print(f"on-domain min={min(on):.3f}  off-domain max={max(off):.3f}")
        if min(on) - max(off) > 0.01:
            print(f"SUGGESTED min_similarity: midpoint {((min(on) + max(off)) / 2):.3f}")
        else:
            print("overlap/adjacent: choose the floor per the trade you want;")
            print("below-floor = silence, above-floor = offers the model must dismiss.")
    elif not on:
        print("no on-domain vector-only candidates found — check probe queries.")


if __name__ == "__main__":
    main()
