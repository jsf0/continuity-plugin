# Changelog

All notable changes to Hermes Continuity Memory are documented here.

This project uses pre-1.0 semantic versioning. Minor versions may change plugin
behavior while the provider API is still stabilizing.

## 0.1.4 — 2026-11-05

### Added

- `strong_fts_anchor_reranker_bypass` gate (default on): a strong bm25
  match (fts_score >= 0.7) survives a cold cross-encoder verdict, mirroring
  the existing exact-context-identifier and strong-personal-anchor
  bypasses. Local cross-encoders under-score terse, metadata-style records
  that genuinely answer a query (observed: an oil-eval record for the EJ257
  scored 0.0027 for an oil question while a record merely quoting the query
  verbs scored 0.896).
- `graph_inclusion_respects_reranker` gate with `graph_reranker_respect_floor`
  (default 0.005): records the cross-encoder scored essentially zero are no
  longer resurrected as association-graph neighbors (observed: browser
  mirrors rejected at 3.7e-5 re-entered as neighbors of other browser
  records). Cold-but-nonzero records remain graph-rescuable by design.

### Fixed

- Text-anchor scoring in `_apply_metadata_score` is now IDF-weighted per
  matched token (reference: IDF of a df=1 term), so corpus-generic filler
  earns almost no text credit instead of a flat +0.35 per token — the
  lexical half of the association-hub noise problem. Corpus statistics are
  computed once per retrieval and shared with dynamic expansion.

## 0.1.3 — 2026-11-05

### Fixed

- FTS bm25 rank-to-score conversion was inverted: SQLite's `bm25()` returns
  negative ranks where more negative is a BETTER match, but the pipeline
  converted with `abs(rank)` and `1/(1+abs)`, so the best FTS match received
  the least credit (observed: top bm25 hit for "oil" scored 0.20 while a
  filler-token match scored 0.42). Ranks now convert monotonically
  (`magnitude/(magnitude+1)`), bounded in (0, 1). Several test assertions
  that encoded the inverted ordering (exact seed orderings, a calibrated
  eval top-k miss, and one mirror-suppression reason label) were updated to
  test their underlying intent instead.

## 0.1.2 — 2026-11-05

### Added

- `continuity_rebuild_associations` tool: drop and recreate all association
  graph edges under current scoring rules (needed after scoring changes and
  to clear co-retrieval-reinforced stale edges).
- Ownership-query vector rescue: first-person questions with ownership verbs
  ("what car do I drive?") relax the weak-vector-only gate to half threshold
  for personal-kind records.
- Regression tests for ownership rescue, the "handle" preference-token bug,
  generic-verb expansion anchors, and IDF-anchored association edges.

### Fixed

- Association edges: anchor bonuses no longer granted flat for ANY entity
  overlap. Bonuses scale with the share of IDF mass carried by non-generic
  shared terms (a term in >20% of records earns no anchor credit), and IDF
  is computed over the whole corpus instead of the candidate pool. This
  removes graph hubs that activated on unrelated queries.
- "handle" removed from preference-intent tokens: procedural questions
  ("how do we handle firmware updates…") were being tagged as personal
  preference queries, rejecting their own project records as
  facet-incompatible.
- Dynamic expansion no longer harvests terms from candidates anchored only
  on generic verbs ("use", "get", "need", …).
- README/INSTALL/install.sh now document the required
  `hermes plugins enable continuity` step (provider setting and plugin
  enable are independent switches).
- `scripts/smoke-test.sh` falls back to the in-repo provider when the real
  Hermes loader's dependencies are absent from the checkout venv.
- `plugin.yaml` in the repository now carries the
  `python_dependencies` declaration (sentence-transformers) that the
  production install already required; version bumped to match.
- Repository-wide ruff format/lint drift fixed; documented development
  commands pass from a fresh clone.

## 0.1.1 — 2026-11-04

### Fixed

- Embedding backend breakage after Hermes updates: `plugin.yaml` now declares
  `python_dependencies` so the package manager installs sentence-transformers
  into the shared plugin environment.

## 0.1.0 — 2026-05-17

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
- Review-first corpus ingestion pipeline for local files, notes, markdown/text,
  and manpage-style sources, with temporary validation and explicit import.
- Pinned system-prompt records plus compact provider-owned continuity guidance that
  remains active even when pinned records are disabled.
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
- Corpus ingestion is offline and review-first; it does not automatically index
  live repositories or private documents in the background.
- No broad LLM-based automatic session summarization yet.
- No multi-user ACL model.
- No automatic skill loading from skill links.
