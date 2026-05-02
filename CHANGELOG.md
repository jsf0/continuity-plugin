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
  `continuity_add`, and `continuity_delete`.
- Session observation storage and conservative marker-based extraction.
- Project capsules for active project state.
- Optional dependency-free SQLite hashed vector backend.
- Built-in Hermes memory write mirroring via `on_memory_write()`.
- Skill links from continuity records to relevant Hermes skill names.
- Install, smoke-test, release, troubleshooting, and configuration docs.
- GitHub Actions CI workflow.

### Security

- Redacts obvious secrets in stored observations and mirrored built-in memory
  writes.
- Rejects obvious prompt-injection-like content in conservative extraction and
  mirroring paths.
- Keeps retrieved continuity context compact and source-linked.

### Known limitations

- No neural embeddings backend yet.
- No repository/document ingestion yet.
- No broad LLM-based automatic session summarization yet.
- No multi-user ACL model.
- No automatic skill loading from skill links.
