# Troubleshooting

## Provider does not load

Check install location:

```bash
printf '%s\n' "${HERMES_HOME:-$HOME/.hermes}/plugins/continuity"
```

The directory should contain files like:

```text
__init__.py
plugin.yaml
models.py
store.py
retrieval.py
```

Reinstall from the repository root:

```bash
./scripts/install.sh
```

Then restart Hermes or start a new session.

## `continuity_status` says provider is not initialized

The provider was discovered but not initialized by Hermes. Confirm Hermes config selects this provider:

```yaml
memory:
  provider: continuity
```

Start a fresh Hermes session after changing config.

## No memories are retrieved

Common reasons:

- No durable `ContextRecord`s exist yet.
- Query score is below `min_score`.
- Current project scope differs from the record's scope.
- The memory was stored only as a `session_observation`, not a durable record.
- The record is archived, retracted, or expired.
- Retrieval gates rejected the candidate as weak vector-only, low-information, incompatible facet, or weak association-graph activation.

Ways to add durable records today:

- `continuity_add`
- explicit session markers:
  - `Remember: ...`
  - `Lesson learned: ...`
  - `Decision: ...`
- Hermes built-in memory writes mirrored through `on_memory_write()`

Inspect manually with:

```text
continuity_status
continuity_search
continuity_get
continuity_debug_retrieval
```

## A memory exists but is not injected

Use `continuity_debug_retrieval` with the exact user query. Compare:

1. whether the record appears as a first-stage candidate;
2. whether it was rejected by score, reranker, facet, stale, or anchor gates;
3. whether an association graph edge tried to include it;
4. whether it was cut by budget, activation threshold, or stale/lifecycle status.

Search can prove storage works; debug retrieval explains whether automatic prefetch selected the record for that exact wording.

## Prefetch output is too large or too small

Tune:

```yaml
memory:
  continuity:
    max_records: 5
    max_chars: 1800
    min_score: 0.1
    include_sources: true
    include_scores: false
```

For debugging, temporarily set:

```yaml
include_scores: true
```

## Vector mode does not improve recall

Check status:

```json
{
  "vector_enabled": true,
  "vector_available": true,
  "vector_count": 29,
  "records_missing_vectors": 0
}
```

If `vector_count` is zero, no records have been indexed since vector mode was enabled. Re-add records, call `continuity_reindex_vectors`, or restart the provider so initialization indexes existing records.

Remember: vectors are candidate generators, not truth. The retriever intentionally rejects weak vector-only matches unless they have sufficient exact anchors or very strong relevance.

## Sentence-transformers backend is unavailable

Install optional dependencies:

```bash
uv sync --extra embeddings --dev
```

Or use the dependency-free backend:

```yaml
memory:
  continuity:
    vector:
      enabled: true
      backend: sqlite-hash
      embedding_model: hash-v1
```

For reranking, configure a supported local cross-encoder only after dependencies are installed:

```yaml
memory:
  continuity:
    reranker:
      enabled: true
      backend: sentence-transformers
      model: BAAI/bge-reranker-base
```

## Association graph retrieves noisy neighbors

The graph is designed to rescue implicit context, so associated neighbors are broader and lower-confidence than direct hits. If output is noisy:

- inspect `continuity_debug_retrieval` activation traces;
- inspect `continuity_association_edges` for broad edges;
- lower `association_graph.max_hops` or `out_degree_cap`;
- raise `association_graph.activation_threshold`;
- disable `association_graph.enabled` temporarily to compare direct retrieval behavior.

Noisy persisted edges may need rebuilding after retrieval or edge-creation logic changes.

## Skill links are not shown

Skill links are only shown when a retrieved record has associated links. Add a record with `skill_links`, then search or prefetch it:

```json
{
  "skill_links": [
    {
      "skill_name": "devops/openbsd-rust-dev-loop",
      "reason": "Relevant for OpenBSD Rust verification.",
      "confidence": 0.95
    }
  ]
}
```

Prefetch shows compact skill hints to avoid prompt bloat. Continuity does not automatically load skills.

## Stale or duplicate memories are active

Prefer lifecycle operations over immediate hard deletion:

```text
continuity_prune_stale dry_run=true
continuity_archive
continuity_restore
continuity_delete
```

`continuity_prune_stale` dry-runs by default. Use archive mode for normal cleanup and reserve hard delete for clearly wrong or sensitive records.

## Secrets in stored content

The plugin redacts obvious secret patterns in observations and mirrored built-in memory writes. It is not comprehensive DLP.

If sensitive data is accidentally stored, delete the record:

```text
continuity_delete
```

Or remove the database if you intentionally want to wipe all continuity memory:

```bash
rm -rf "${HERMES_HOME:-$HOME/.hermes}/continuity"
```

## Tests fail because `uv` is missing

Install `uv` from Astral, then run:

```bash
uv sync --dev
uv run pytest tests/ -q
```

Without `uv`, use an existing Python 3.11+ environment with `pytest` and `ruff` installed.
