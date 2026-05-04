# Changelog

All notable changes to Hermes Continuity Memory are documented here.

This project uses pre-1.0 semantic versioning. Minor versions may change plugin
behavior while the provider API is still stabilizing.

## 0.1.0 — Unreleased

### Added

- Standalone Hermes memory provider plugin named `continuity`.
- SQLite local-first continuity database under `$HERMES_HOME/continuity/`.
- Structured `ContextRecord` model with trust levels, scopes, tags, entities,
  source refs, and embedding text.
- SQLite FTS5 retrieval and deterministic metadata scoring.
- Budgeted `prefetch()` output with retrieval event logging.
- Tool surface: `continuity_status`, `continuity_search`, `continuity_get`,
  `continuity_add`, `continuity_delete`, `continuity_archive`,
  `continuity_restore`, and `continuity_prune_stale`.
- Session observation storage and conservative marker-based extraction.
- Project capsules for active project state.
- Optional dependency-free SQLite hashed vector backend and optional
  sentence-transformers embedding backend.
- Optional sentence-transformers cross-encoder reranker for query-record
  precision filtering.
- Association graph storage, inventory, and bounded activation traversal for
  implicit context rescue.
- Built-in Hermes memory write mirroring via `on_memory_write()`.
- Skill links from continuity records to relevant Hermes skill names.
- Stale-memory lifecycle fields (`status`, `superseded_by`, `stale_reason`,
  `archived_at`) with archive/restore and conservative stale-prune tooling.
- Retrieval excludes archived, retracted, and expired records by default while
  allowing explicit `include_stale` inspection.
- Retrieval-noise gates for weak vector-only hits, generic memory-meta queries,
  low-information follow-ups, boilerplate mirrored memory titles, and weak
  association-graph activation anchors.
- Install, smoke-test, release, troubleshooting, and configuration docs.
- GitHub Actions CI workflow.

### Security

- Redacts obvious secrets in stored observations and mirrored built-in memory
  writes.
- Rejects obvious prompt-injection-like content in conservative extraction and
  mirroring paths.
- Keeps retrieved continuity context compact and source-linked.

### Known limitations

- Neural embeddings, reranking, and association graph traversal are optional
  local backends that require extra dependencies and tuning.
- No repository/document ingestion yet.
- No broad LLM-based automatic session summarization yet.
- No multi-user ACL model.
- No automatic skill loading from skill links.
