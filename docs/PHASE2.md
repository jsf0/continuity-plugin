# Phase 2 Notes

## Completed

- Added `continuity.models` with:
  - `SourceRef`
  - `ContextRecord`
  - allowed record kinds and trust levels
  - dict round-tripping and default `embedding_text` generation

- Added `continuity.store` with:
  - SQLite migration version 1
  - `context_records`
  - `context_records_fts`
  - `session_observations`
  - `retrieval_events`
  - CRUD operations
  - FTS maintenance on upsert/delete

- Added `continuity.retrieval` with:
  - FTS candidate generation
  - tag/entity/text/scope/confidence/importance scoring
  - deterministic top-k ordering
  - Phase 2 eval fixture support

- Wired provider initialization to create and migrate:

```text
$HERMES_HOME/continuity/continuity.db
```

## Verification

```text
uv run ruff check .      ✅
uv run pytest tests/ -q  ✅ 24 passed
```

## Intentional non-goals for Phase 2

- `prefetch()` remains no-op until Phase 3.
- Automatic context injection formatting remains deferred.
- Session consolidation remains deferred.
- Vector retrieval remains deferred.
