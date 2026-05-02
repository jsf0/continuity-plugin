# Phase 7 — optional vector / hybrid retrieval

Phase 7 adds an optional vector retrieval layer without making embeddings or a
vector database mandatory.

## Implemented

- Added `continuity.embeddings`:
  - `VectorBackend` protocol
  - `VectorHit`
  - `SQLiteHashVectorBackend`
  - deterministic signed feature-hashing embeddings
  - cosine similarity search over persisted SQLite vector rows

- Added SQLite vector persistence:
  - `context_record_vectors`
  - `ContinuityStore.upsert_vector()`
  - `ContinuityStore.delete_vector()`
  - `ContinuityStore.list_vectors()`
  - `ContinuityStore.count_vectors()`

- Added hybrid retrieval:
  - FTS candidates remain the baseline.
  - Metadata scoring remains unchanged for exact/tag/entity/project matches.
  - Optional vector hits add candidates and a bounded score component.
  - Stale vector hits are ignored and deleted.

- Added provider integration:
  - vector backend is created only when configured
  - existing records are indexed at initialization
  - `continuity_add` indexes records when vector mode is enabled
  - `continuity_delete` removes vector rows
  - `prefetch()` and `continuity_search` use hybrid retrieval when available
  - status now reports backend, availability, vector row count, and Phase 7 marker

## Configuration

Vector retrieval is disabled by default:

```yaml
memory:
  provider: continuity
  continuity:
    vector:
      enabled: false
      backend: none
```

Enable the dependency-free local backend:

```yaml
memory:
  provider: continuity
  continuity:
    vector:
      enabled: true
      backend: sqlite-hash
      embedding_model: hash-v1
```

Accepted backend aliases for Phase 7:

- `sqlite-hash`
- `hash`
- `sqlite-json`

Unknown backends are clamped to `none`; FTS-only mode remains fully supported.

## Intentional limits

- This is not yet sqlite-vec or LanceDB. It is a local persisted vector backend
  with the same abstraction those backends would implement later.
- Embeddings are deterministic lexical/hashed vectors, not neural embeddings.
- Vector scores supplement retrieval; they do not replace exact/entity/project
  scoring.
- The plugin still embeds compact `embedding_text`, not raw transcripts.

## Verification

- Vector tests use both the real SQLite hash backend and a mock vector backend
  for deterministic hybrid-score assertions.
- FTS-only tests continue to pass.
- Provider smoke tests verify vector indexing and search through the real tool
  surface.
