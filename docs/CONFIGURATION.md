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

    retrieval_gates:
      min_base_relevance: 0.35
      min_vector_relevance: 0.05
      min_vector_only_relevance: 2.75
      weak_vector_only: true
      facet_compatibility: true
      memory_meta: true
      low_information: true
      project_status_anchor: true
      personal_project: true
      activation_anchor: true
      strong_personal_anchor_reranker_bypass: true

    pinned_system_prompt:
      enabled: true
      include_records: true
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
mixedbread-ai/mxbai-embed-large-v1
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

## Retrieval gate tuning

The `retrieval_gates` block controls conservative filters that run after candidate generation and before final context injection. Defaults are intentionally precision-first: it is better for continuity to return no memory than to inject a plausible but wrong memory.

Use `continuity_debug_retrieval(query="...", limit=5)` before changing these values. Look at `rejected[].rejected_reason`, `rejected[].tuning_advice`, `selected[].reasons`, scores, and `activation_trace.cut_neighbors[].reason`; tune one setting at a time and then rerun regression/demo queries.

Example debug excerpt:

```json
{
  "id": "r_soft_debug_match",
  "rejected_reason": "below_min_base_relevance",
  "base_relevance": 1.35,
  "tuning_advice": {
    "config": "retrieval_gates.min_base_relevance",
    "try": "If this record should match, lower this threshold slightly or add stronger tags/entities. If weak one-word matches are noisy, raise it."
  }
}
```

That means the record had some lexical/metadata evidence, but not enough to pass the direct retrieval gate. For a true positive, add better tags/entities or lower `retrieval_gates.min_base_relevance` slightly; for a noisy one-word match, raise it.

### `retrieval_gates.min_base_relevance`

Minimum lexical/metadata evidence required before a candidate can survive direct retrieval. This uses FTS, vector score, tag matches, entity matches, and text matches before scope, confidence, importance, reranker, or graph boosts.

Default: `0.35`.

Plain English:

- If relevant records are rejected as `below_min_base_relevance`, try lowering this slightly, for example `0.35 -> 0.25`.
- If vague queries pull barely related records because of one weak word match, raise it, for example `0.35 -> 0.5`.
- Do not use this to fix reranker misses; tune `reranker.min_score` or `strong_personal_anchor_reranker_bypass` instead.

### `retrieval_gates.min_vector_relevance`

Minimum raw vector similarity before a vector hit is considered at all.

Default: `0.05`.

Plain English:

- If paraphrases never even appear as candidates in debug output, lower this slightly.
- If lots of semantically mushy vector hits appear in debug output, raise it.
- This only matters when vectors are enabled.

### `retrieval_gates.min_vector_only_relevance`

Minimum weighted vector score required when a candidate has no FTS/tag/entity/text anchor.

Default: `2.75`.

Plain English:

- If vector-only paraphrases are useful but show `weak_vector_only_without_anchor`, lower this a little.
- If unrelated memories appear because neural similarity is too generous, raise this.
- Prefer adding better tags/entities to important records before lowering this globally.

### `retrieval_gates.weak_vector_only`

Rejects vector-only candidates that fall below `min_vector_only_relevance`.

Default: `true`.

Plain English:

- Disable only for experiments or very small, clean corpora.
- If you disable this and see noisy memories, turn it back on and tune `min_vector_only_relevance` instead.

### `retrieval_gates.facet_compatibility`

Prevents obvious domain collisions such as software “framework” questions retrieving Framework laptop/desktop memories.

Default: `true`.

Plain English:

- If debug output says `facet_incompatible_candidate` for a record that really is relevant, either improve the record tags/entities or temporarily disable this to confirm the gate is the cause.
- If polysemous words cross domains, keep this enabled.

### `retrieval_gates.memory_meta`

Keeps continuity/memory-system records out of ordinary non-memory queries, and keeps generic memory words from matching unrelated records.

Default: `true`.

Plain English:

- If normal questions retrieve continuity implementation/status records, keep this enabled.
- If an actual memory-system query rejects relevant memory records as `memory_system_record_without_meta_query`, make the query more explicit (`continuity`, `retrieval`, `memory provider`) before disabling this.

### `retrieval_gates.low_information`

Suppresses retrieval for vague follow-ups with no durable anchor, such as “ok”, “how about now”, or “can you test and see if it is better now”.

Default: `true`.

Plain English:

- If vague follow-ups inject stale project context, keep this enabled.
- If short but meaningful local commands in your workflow are being rejected as `low_information_direct_query`, add a stronger project/entity word to the query or lower/disable this only after checking debug output.

### `retrieval_gates.project_status_anchor`

Requires active project-state records to match a non-generic query anchor before selection.

Default: `true`.

Plain English:

- If old project status appears for generic “what now?” style queries, keep this enabled.
- If a project-status record is relevant but rejected as `weak_project_status_candidate`, add specific tags/entities or lower this gate only for a trusted, scoped deployment.

### `retrieval_gates.personal_project`

Prevents first-person/personal queries from drifting into unrelated project status, and prevents broad graph edges from crossing between personal facts and project records without anchors.

Default: `true`.

Plain English:

- If “what do I prefer?” retrieves random project roadmap records, keep this enabled.
- If a personal query intentionally needs project context, make the query include the project/entity name before disabling this.

### `retrieval_gates.activation_anchor`

Requires rejected reranker candidates to have a strong non-generic query anchor before they can seed association-graph traversal.

Default: `true`.

Plain English:

- If association graph rescue is too quiet and debug shows `weak_anchor_activation_seed` for a relevant candidate, improve tags/entities first; then consider disabling this for experiments.
- If graph traversal fans out through old broad associations, keep this enabled.

### `retrieval_gates.strong_personal_anchor_reranker_bypass`

Lets strongly tagged/entity-matched personal records survive a low reranker score. This compensates for generic cross-encoders that often under-score short personal setup/preference facts.

Default: `true`.

Plain English:

- If personal facts like vehicle/setup/preferences are rejected as `below_min_reranker_score` despite strong tag/entity matches, keep this enabled.
- If personal records bypass the reranker too aggressively, disable this or improve tags/entities so only truly strong anchors match.

### `retrieval_gates.self_referential_echo_penalty` / `retrieval_gates.self_referential_echo_weight`

Demotes memory-system records that match a non-memory query only by echoing the query's own tokens. Fix/debug notes about the memory system routinely embed the colloquial query they document ("what oil should I use"), which made them win FTS on that query and outrank the genuine answer records. When a `memory_system`-facet record contains every content token of a non-memory query of three or more raw words, a penalty of `self_referential_echo_weight * base_relevance` (default weight `1.0`, i.e. the echo-driven lexical score is zeroed) is subtracted. The record is demoted, not rejected. Memory-facet queries and non-memory records are exempt.

Default: `true` / `1.0`.

Plain English:

- If a fix-note about retrieval outranks the real answer on a non-memory query, keep this enabled and check the note carries the `self_referential_echo` reason in `continuity_debug_retrieval`.
- If a memory note is a legitimate answer to a non-memory query but keeps getting demoted, lower the weight (e.g. `1.0 -> 0.5`) or, better, rephrase the note so it stops quoting colloquial queries verbatim.
- Do not disable this to make debug notes reachable; ask memory questions with memory words (`continuity`, `retrieval`, `plugin`) instead — those are exempt.

### Tuning workflow

1. Run `continuity_debug_retrieval` for a failing positive query and a nearby negative/noise query.
2. Identify the rejection reason or noisy selected reason.
3. Change one value by a small amount.
4. Rerun the same positive and negative queries.
5. Run `./scripts/demo-retrieval.sh --quiet` and the retrieval regression tests before keeping the change.

Recommended command after tuning:

```bash
uv run pytest tests/test_retrieval.py tests/test_retrieval_public_regressions.py tests/test_association_graph.py -q
./scripts/demo-retrieval.sh --quiet
```

## Pinned system prompt options

The provider always returns a compact continuity guidance block from `system_prompt_block()` when initialized. Pinned records are enabled by default as the Tier 0 memory layer. For small/local models that need continuity operating guidance but should not receive any always-on memory summaries, set `pinned_system_prompt.enabled: true` and `pinned_system_prompt.include_records: false`.

### `pinned_system_prompt.enabled`

Whether the pinned system-prompt feature is enabled. The compact continuity operating guidance remains available when the provider is initialized; record summaries are controlled separately by `include_records`.

Default: `true`.

### `pinned_system_prompt.include_records`

Whether high-importance continuity records are included after the guidance block. Set this to `false` for guidance-only mode: the model learns how to use continuity, but no durable memory summaries are injected into the system prompt.

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
