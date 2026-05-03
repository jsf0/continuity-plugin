# Configuration

Minimal Hermes config:

```yaml
memory:
  provider: continuity
```

Hermes passes provider-specific configuration to `ContinuityProvider.initialize()`
as `continuity_config`. The exact YAML nesting depends on Hermes' config loader,
but the intended shape is:

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
```

## Options

### `max_records`

Maximum selected continuity records to consider for prefetch output.

Default: `5`.

### `max_chars`

Hard character budget for injected prefetch output.

Default: `1800`.

Values below `200` are clamped to `200`.

### `min_score`

Minimum retrieval score required before a record can be included in prefetch.

Default: `0.1`.

### `include_sources`

Whether prefetch output includes source refs.

Default: `true`.

### `include_scores`

Whether prefetch output includes retrieval scores.

Default: `false`.

Useful for debugging retrieval quality; noisy for normal use.

### `save_turn_observations`

Whether `sync_turn()` stores sanitized per-turn observations for later
consolidation.

Default: `true`.

### `consolidate_on_session_end`

Whether `on_session_end()` extracts explicit durable memories from marker
phrases.

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

Current accepted values:

```text
per-repo
per-directory
global
per-session
```

Default: `per-repo`.

### `observation_max_chars`

Maximum stored characters per user/assistant observation field.

Default: `4000`.

### `stale_after_days`

Age threshold used by `continuity_prune_stale` for conservative low-importance
candidate detection.

Default: `180`.

This is not an automatic destructive retention policy. Normal retrieval excludes
records with `status != active` and records whose `expires_at` is in the past.
`continuity_prune_stale` dry-runs by default, reports candidates and reasons,
and only mutates records when called with `dry_run: false`.

### `vector.enabled`

Enables optional vector/hybrid retrieval.

Default: `false`.

### `vector.backend`

Supported Phase 7 backend aliases:

```text
none
sqlite-hash
hash
sqlite-json
```

Unknown values are clamped to `none`.

`sqlite-hash` is dependency-free and stores deterministic hashed vectors in
SQLite. It is not a neural embedding backend.

### `vector.embedding_model`

Model label for vector rows. With the current backend, use:

```text
hash-v1
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
