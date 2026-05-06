# Configuration

Minimal Hermes config:

```yaml
memory:
  provider: continuity
```

Hermes passes provider-specific configuration to `ContinuityProvider.initialize()` as `continuity_config`. The intended YAML shape is:

```yaml
memory:
  provider: continuity
  continuity:
    max_records: 5
    max_chars: 1800
    min_score: 0.1
    include_sources: true
    include_scores: false
    save_turn_observations: true
    consolidate_on_session_end: true
    consolidate_min_turns: 3
    session_strategy: per-repo
    project_scope_boost: 1.0
    stale_after_days: 180
    observation_max_chars: 4000

    vector:
      enabled: false
      backend: none
      embedding_model: null
      batch_size: 32
      normalize: true

    reranker:
      enabled: false
      backend: none
      model: null
      min_score: 0.15
      weight: 2.0
      top_k: 20

    association_graph:
      enabled: true
      edge_creation_threshold: 0.25
      out_degree_cap: 20
      hop_decay: 0.6
      activation_threshold: 0.3
      max_hops: 2

    pinned_system_prompt:
      enabled: true
      max_chars: 1200
      max_records: 5
      kinds: [user_preference, project_convention]
      min_importance: 0.75

    dream:
      enabled: false
      schedule: "03:30"
      timezone: "UTC"
      mode: "report"
      max_archives_per_run: 20
      run_on_initialize: false
      run_on_turn: false
```

## Top-level options

## Production memory model

The recommended production setup is continuity-exclusive: configure Hermes with
`memory.provider: continuity` and treat continuity as the primary memory source.
Stock Hermes memory files can be imported or mirrored for migration, but they
should not remain a competing always-on prompt context. Tier 0 pinned continuity
records replace the tiny trusted memory kernel; ordinary continuity retrieval
handles the long tail per turn.

Keep Tier 0 small and auditable. It should contain durable high-trust facts such
as stable user preferences and important project conventions, not broad logs or
large status dumps.

### `max_records`

Maximum selected continuity records to consider for prefetch output.

Default: `5`.

### `max_chars`

Hard character budget for injected prefetch output.

Default: `1800`. Values below `200` are clamped to `200`.

### `min_score`

Minimum retrieval score required before a record can be included in prefetch.

Default: `0.1`.

### `include_sources`

Whether prefetch output includes source refs.

Default: `true`.

### `include_scores`

Whether prefetch output includes retrieval scores.

Default: `false`. Enable temporarily when debugging retrieval quality.

### `save_turn_observations`

Whether `sync_turn()` stores sanitized per-turn observations for later consolidation.

Default: `true`.

### `consolidate_on_session_end`

Whether `on_session_end()` extracts explicit durable memories from marker phrases.

Default: `true`.

Current markers:

```text
Remember: ...
Lesson learned: ...
Decision: ...
```

### `consolidate_min_turns`

Minimum number of user turns before session-end extraction runs.

Default: `3`.

### `session_strategy`

Accepted values:

```text
per-repo
per-directory
global
per-session
```

Default: `per-repo`.

### `project_scope_boost`

Score boost for records scoped to the current project.

Default: `1.0`.

### `observation_max_chars`

Maximum stored characters per user/assistant observation field.

Default: `4000`.

### `stale_after_days`

Age threshold used by `continuity_prune_stale` for conservative low-importance candidate detection.

Default: `180`.

This is not an automatic destructive retention policy. Normal retrieval excludes records with `status != active` and records whose `expires_at` is in the past. `continuity_prune_stale` dry-runs by default and only mutates records when called with `dry_run: false`.

## Vector options

### `vector.enabled`

Enables optional vector/hybrid retrieval.

Default: `false`.

### `vector.backend`

Supported aliases:

```text
none
sqlite-hash
hash
sqlite-json
sentence-transformers
```

Unknown values are clamped to `none`.

`sqlite-hash` is dependency-free and stores deterministic hashed vectors in SQLite. `sentence-transformers` uses local neural embeddings and requires the `embeddings` extra or equivalent packages.

### `vector.embedding_model`

Model label or sentence-transformers model name.

Examples:

```text
hash-v1
BAAI/bge-small-en-v1.5
```

### `vector.batch_size`

Batch size for embedding/indexing operations.

Default: `32`.

### `vector.normalize`

Whether embedding vectors should be normalized when the backend supports it.

Default: `true`.

## Reranker options

### `reranker.enabled`

Enables query-record reranking after candidate retrieval.

Default: `false`.

### `reranker.backend`

Supported aliases:

```text
none
sentence-transformers
cross-encoder
```

### `reranker.model`

Cross-encoder model name. Common local default:

```text
BAAI/bge-reranker-base
```

### `reranker.min_score`

Minimum reranker score for direct automatic selection.

Default: `0.15`.

### `reranker.weight`

Score weight added from reranker results.

Default: `2.0`.

### `reranker.top_k`

Maximum candidate count to rerank.

Default: `20`.

## Association graph options

The association graph is additive: it can rescue implicit context related to strong direct or activation-only seeds, but retrieved graph neighbors are lower-confidence context.

### `association_graph.enabled`

Default: `true`.

### `association_graph.edge_creation_threshold`

Minimum deterministic overlap score for creating an association edge between records.

Default: `0.25`.

### `association_graph.out_degree_cap`

Maximum neighbor edges considered per source record during graph traversal.

Default: `20`.

### `association_graph.hop_decay`

Activation decay applied per hop.

Default: `0.6`.

### `association_graph.activation_threshold`

Minimum activation required for an associated neighbor to be eligible for injection.

Default: `0.3`.

### `association_graph.max_hops`

Maximum traversal depth.

Default: `2`.

## Pinned system prompt options

The provider always returns a compact continuity guidance block from `system_prompt_block()` when initialized. Pinned records are enabled by default as the Tier 0 memory layer; disable them explicitly if you want retrieval-only continuity.

### `pinned_system_prompt.enabled`

Whether high-importance continuity records are included in the system prompt at session start.

Default: `true`.

### `pinned_system_prompt.max_chars`

Character budget for pinned records only, not the provider guidance block.

Default: `1200`.

### `pinned_system_prompt.max_records`

Maximum number of records to pin.

Default: `5`.

### `pinned_system_prompt.kinds`

Record kinds eligible for pinning.

Default: `[user_preference, project_convention]`.

### `pinned_system_prompt.min_importance`

Minimum record importance required for pinning.

Default: `0.75`.

## Dream maintenance options

The dream cycle is offline/report-oriented memory maintenance. It checks stale candidates, recomputed quality-warning inventory, vector index parity, and association-graph edge inventory. Report mode does not mutate records; archive modes only soft-archive and never hard-delete.

### `dream.enabled`

Whether scheduled dream checks are enabled. Scheduling is evaluated during provider initialization and/or turn sync when the matching `run_on_*` option is enabled; Hermes does not run plugin code on an independent wall-clock timer by itself.

Default: `false`.

### `dream.schedule`

Local `HH:MM` time after which a scheduled dream can run once per day.

Default: `03:30`.

### `dream.timezone`

IANA timezone for `dream.schedule`.

Default: `UTC`.

### `dream.mode`

Accepted values:

```text
report
archive-safe
archive-all-candidates
```

Start with `report`. Archive modes soft-archive deterministic stale candidates and still never hard-delete.

Default: `report`.

### `dream.run_on_initialize` / `dream.run_on_turn`

Whether the provider should check the schedule during initialization or turn sync.

Default: `false` for both.

Report-only example:

```yaml
memory:
  provider: continuity
  continuity:
    dream:
      enabled: true
      schedule: "03:30"
      timezone: "UTC"
      mode: "report"
      run_on_turn: true
      run_on_initialize: true
```

## Runtime DB

Continuity stores data at:

```text
$HERMES_HOME/continuity/continuity.db
```

Main tables:

- `context_records`
- `context_records_fts`
- `session_observations`
- `retrieval_events`
- `context_record_vectors`
- `context_record_skill_links`
- `context_record_association_edges`
