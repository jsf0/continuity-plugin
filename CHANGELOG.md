# Changelog

All notable changes to Hermes Continuity Memory are documented here.

This project uses pre-1.0 semantic versioning. Minor versions may change plugin
behavior while the provider API is still stabilizing.

## 0.1.9 — 2026-11-05

### Fixed

- Prefetch injection budget no longer lets record LENGTH subvert score order.
  `_format_prefetch_context` filled the max_chars budget greedily and SKIPPED
  any hit that did not fit, so a long top-ranked record could consume the
  budget and get the #2 hit silently dropped while smaller, lower-scored
  records slipped in. Observed live (autocross/HPDE session): the user's car
  record ranked #2 by retrieval score but was skipped at injection because
  the #1 firmware note was long, and the assistant then told the user "I don't
  have your car on record" — while an explicit continuity_search found it
  instantly. Hits that do not fit are now truncated to the remaining budget
  (>=100-char fragment) instead of dropped. 3 regression tests in
  tests/test_prefetch_budget.py.

### Notes

- Live-store fix for the same session: the car record's text never contained
  the word "car", so every "my car" question was unreachable by FTS and
  died at the weak-vector-only gate when the query lacked ownership verbs
  ("what maintenance do I need for my car" — no drive/own/use). The record
  now contains "car"/"vehicle" and ranks #1 on those queries. General lesson
  (already in the skill): records about a thing should contain the colloquial
  noun users type, not just proper nouns.

## 0.1.8 — 2026-11-05

### Added

- Self-referential echo penalty (`retrieval_gates.self_referential_echo_penalty`,
  default on; `self_referential_echo_weight`, default 1.0 = fraction of base
  relevance subtracted). Memory-system fix/debug notes often embed the exact
  colloquial query they document ("what oil should I use"), so they won FTS on
  that query and outranked the genuine answer records — observed live: a
  retrieval fix-note scored 17.9 on an oil question while the car's oil-spec
  record scored 7.0. When a memory_system-facet record contains every content
  token of a non-memory multi-word query, its lexical score is demoted
  proportionally (not rejected — it may still be a legitimate answer).
  Memory-facet queries are exempt, non-memory records are exempt, and queries
  under three raw words are exempt. Live A/B: the oil-spec record went from #5
  to #1 on "what oil should I use"; fix-notes dropped out of the top-5 on the
  oil, car, and backup queries while remaining fully rankable on memory-system
  queries. Five regression tests in tests/test_self_referential_echo.py.

## 0.1.7 — 2026-11-05

### Added

- Incremental vector indexing: `upsert()` stores a sha256 of the embedding
  text (new `context_record_vectors.text_hash` column, added by an idempotent
  migration) and skips the model call when the stored vector was built from
  identical text. Previously every provider initialization re-embedded the
  entire corpus — O(corpus) model calls per gateway restart, which is
  minutes-scale with a large neural embedder. Startup embed cost is now
  O(new/changed records); legacy rows without a hash are re-embedded once,
  then skipped. Live-verified: a second restart embedded zero records.

### Changed

- README now recommends `mixedbread-ai/mxbai-embed-large-v1` as the optional
  embedding model, based on a labeled bake-off on a real 77-record continuity
  corpus (18 paraphrase-style queries, per-model query prefixes, cosine
  ranking on production `embedding_text`): 18/18 candidate recall@20, MRR
  0.71, worst-case rank 11 — versus `bge-small-en-v1.5` at 17/18, worst-case
  rank 42 (one relevant record fell entirely outside the reranker window).
  `bge-base` measured worse than `bge-small` on this corpus; `e5-small-v2`
  and `all-MiniLM-L6-v2` also evaluated. mxbai needs no query-side prefix
  (the bge family does, for best retrieval quality).

## 0.1.6 — 2026-11-05

### Fixed

- The provider expected a `continuity_config` kwarg that Hermes core never
  passes: `MemoryManager.initialize_all()` forwards only session-scoping
  kwargs, so the plugin silently ran with all-default config — vector and
  reranker backends disabled despite being enabled in config.yaml. The
  provider now self-loads the `memory.continuity` config section via
  `hermes_cli.config.load_config()` (best-effort, profile-aware) when the
  kwarg is absent.
- `plugin.yaml` now declares `python_dependencies` (sentence-transformers)
  in the repo. The equivalent installed-copy-only hotfix from Nov 3 was
  silently wiped by every repo deployment, and the package-manager sync
  then dropped the dependency from the shared gateway environment.

## 0.1.5 — 2026-11-05

### Changed

- README now recommends `mixedbread-ai/mxbai-rerank-base-v2` as the
  optional reranker model, based on a labeled-pair evaluation on a real
  150-record continuity corpus: 25/25 correct with a wide margin at the
  default 0.15 threshold, versus `bge-reranker-base` (24/25, misses terse
  metadata records) and `bge-reranker-v2-m3` (25/25 but compressed
  calibration requiring min_score ~0.01). No code change; the model is a
  configuration value.

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
