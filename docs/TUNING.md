# Tuning retrieval

This guide explains the main retrieval knobs in plain English. For the full config reference, see `docs/CONFIGURATION.md`.

Start with the defaults. Tune only when you see a concrete symptom, and use `continuity_debug_retrieval` to confirm why a record was selected or rejected.

## Recommended first-install config

This stays dependency-free while enabling local hashed vectors and graph rescue:

```yaml
memory:
  provider: continuity
  continuity:
    max_records: 5
    max_chars: 1800
    min_score: 0.1
    include_sources: true
    include_scores: false

    vector:
      enabled: true
      backend: sqlite-hash

    reranker:
      enabled: false
      backend: none

    association_graph:
      enabled: true
```

## How to debug before changing settings

1. Confirm records exist:

   ```text
   continuity_status
   continuity_search(query="the thing you expected to remember")
   ```

2. Ask why automatic retrieval behaved the way it did:

   ```text
   continuity_debug_retrieval(query="the exact user wording")
   ```

3. Look for rejection reasons and budget cuts before changing thresholds.

Search proves storage works. Debug retrieval explains candidate scoring, gate rejections, graph activation, stale/lifecycle filtering, and prompt-budget cuts for one exact query.

## Prompt budget knobs

### `max_records`

How many selected memories can be considered for the prompt.

Default: `5`.

- Raise it if several relevant records exist but only one or two are being considered.
- Lower it if the model gets too much background context.
- Typical range: `3` to `8`.

### `max_chars`

Maximum characters of continuity memory injected into the prompt.

Default: `1800`.

- Raise it if selected records are omitted because the prompt block is too small.
- Lower it if memory context distracts smaller/local models.
- Typical range: `1000` to `3000`.

### `include_sources`

Whether prompt memory includes compact source references.

Default: `true`.

- Keep on when you want better verification and hydration habits.
- Turn off for very small context budgets.

### `include_scores`

Whether prompt memory includes retrieval scores.

Default: `false`.

- Turn on temporarily when debugging retrieval quality.
- Keep off for normal use to avoid distracting the model.

## Selection threshold

### `min_score`

The minimum final score required before a record can be included.

Default: `0.1`.

This is a final safety threshold after candidate retrieval and scoring. Most precision/recall tuning should happen with the specific retrieval gates below rather than by changing only `min_score`.

- Raise it if obviously weak records still get injected.
- Lower it only if debug retrieval shows useful records are just below the final cutoff.

## Retrieval gates

Retrieval gates are conservative filters that reduce noisy memory activation. They are especially important when vectors and graph expansion are enabled.

### `retrieval_gates.min_base_relevance`

Plain English: reject candidates that barely match the query before vector/graph rescue.

Default: `0.35`.

Debug symptom: `below_min_base_relevance`.

- Raise it for less noise.
- Lower it if exact-but-sparse queries miss relevant records.
- Typical range: `0.25` to `0.50`.

### `retrieval_gates.min_vector_relevance`

Plain English: minimum vector similarity contribution before vector evidence matters.

Default: `0.05`.

- Raise it if vectors contribute too much weak evidence.
- Lower it if semantic matches are ignored too often.

### `retrieval_gates.min_vector_only_relevance`

Plain English: how strong a vector-only match must be when text search has little support.

Default: `2.75`.

Debug symptom: weak vector-only matches appear or are rejected.

- Raise it if semantic search pulls unrelated memories.
- Lower it if paraphrases and synonyms fail despite being obviously relevant.
- Typical range: `2.25` to `3.50`.

### `retrieval_gates.weak_vector_only`

Plain English: reject vector-only candidates unless they are strong enough.

Default: `true`.

Keep this on for public/default use. Turn it off only for experiments where recall matters more than precision.

### `retrieval_gates.facet_compatibility`

Plain English: reject candidates whose broad facet does not match the query intent.

Default: `true`.

This helps avoid mixing personal preferences, project state, docs, and memory-meta queries when the query clearly points elsewhere.

### `retrieval_gates.memory_meta`

Plain English: avoid treating generic questions about memory behavior as requests for arbitrary stored memories.

Default: `true`.

Keep this on unless you are debugging memory-system records specifically.

### `retrieval_gates.low_information`

Plain English: suppress weak retrieval for short follow-ups like “what about that?” when there is not enough anchor text.

Default: `true`.

Keep this on for safer behavior with ambiguous follow-up turns.

### `retrieval_gates.project_status_anchor`

Plain English: require enough project anchor evidence before injecting project-status records.

Default: `true`.

This reduces stale or wrong-project status leaks.

### `retrieval_gates.personal_project`

Plain English: avoid mixing personal/user-preference records with project records unless query evidence supports it.

Default: `true`.

### `retrieval_gates.activation_anchor`

Plain English: require strong enough anchors before association-graph neighbors can activate.

Default: `true`.

Keep this on when the association graph is enabled.

### `retrieval_gates.strong_personal_anchor_reranker_bypass`

Plain English: allow strongly anchored personal records to survive reranker behavior that may under-score preferences.

Default: `true`.

## Vector settings

### `vector.enabled`

Turns on vector/hybrid retrieval.

Default in config parser: `false`. Recommended first-install setting: `true` with `sqlite-hash`.

### `vector.backend`

Options:

- `none` — no vector retrieval.
- `sqlite-hash` — dependency-free hashed vectors stored in SQLite.
- `sentence-transformers` — local neural embeddings, extra dependencies required.

Use `sqlite-hash` first. It gives synonym-ish behavior without installing ML packages.

### `continuity_reindex_vectors`

If you enable vectors after records already exist, run:

```text
continuity_reindex_vectors
```

Then check `continuity_status` for `records_missing_vectors`.

## Reranker settings

Reranking is optional. It can improve precision, but adds dependencies, latency, and another model to tune.

Recommended default:

```yaml
reranker:
  enabled: false
  backend: none
```

Optional local reranker:

```yaml
reranker:
  enabled: true
  backend: sentence-transformers
  model: BAAI/bge-reranker-base
  min_score: 0.15
  weight: 2.0
  top_k: 20
```

Use reranking when you have many plausible candidates and need better final ordering. Do not enable it first when debugging basic install problems.

## Association graph settings

The association graph can pull related records that did not directly match the query. This is useful for source references, project capsules, and records that are connected by shared entities.

### `association_graph.enabled`

Default: `true`.

- Keep on if associated lower-confidence context is helpful.
- Turn off if graph neighbors are noisy.

### `association_graph.activation_threshold`

Plain English: how much evidence is needed before graph neighbors can join the results.

Default: `0.3`.

- Raise it for less graph noise.
- Lower it for more graph recall.

### `association_graph.max_hops`

How far graph traversal can go.

Default: `2`.

For conservative behavior, try `1`.

### `association_graph.out_degree_cap`

How many outgoing edges per seed record can be considered.

Default: `20`.

Lower it if broad records fan out into too many neighbors.

## Pinned Tier 0 settings

Pinned records are always-on memory. They should stay tiny and high-trust.

```yaml
pinned_system_prompt:
  enabled: true
  include_records: true
  max_chars: 1200
  max_records: 5
  kinds: [user_preference, project_convention]
  min_importance: 0.75
```

If you want guidance-only mode with no pinned record summaries:

```yaml
pinned_system_prompt:
  enabled: true
  include_records: false
```

If a small model gets distracted, lower `max_chars` and `max_records`, or set `include_records: false`.

## Common recipes

### Memory feels too noisy

```yaml
memory:
  continuity:
    max_records: 3
    max_chars: 1200
    retrieval_gates:
      min_base_relevance: 0.45
      min_vector_only_relevance: 3.25
    association_graph:
      activation_threshold: 0.45
      max_hops: 1
```

### Memory misses obvious relevant facts

```yaml
memory:
  continuity:
    max_records: 8
    max_chars: 2600
    retrieval_gates:
      min_base_relevance: 0.25
      min_vector_only_relevance: 2.25
```

After changing vector settings, run `continuity_reindex_vectors`.

### Small/local models get distracted by memory

```yaml
memory:
  continuity:
    max_records: 3
    max_chars: 1000
    include_scores: false
    include_sources: false
    pinned_system_prompt:
      max_records: 3
      max_chars: 700
```

### Debug mode

```yaml
memory:
  continuity:
    include_sources: true
    include_scores: true
```

Use this temporarily while inspecting `continuity_debug_retrieval`, then turn scores off again.

### Maximum dependency-free local recall

```yaml
memory:
  continuity:
    vector:
      enabled: true
      backend: sqlite-hash
    association_graph:
      enabled: true
```

This keeps the install lightweight and avoids neural model downloads.

## Tuning checklist

Before changing defaults, ask:

- Does `continuity_search` find the expected record?
- Does `continuity_debug_retrieval` show it as a candidate?
- Was it rejected by a gate, stale lifecycle, reranker score, or budget?
- Is the record scoped to the right project?
- Is the record archived, retracted, or expired?
- If vectors are enabled, does `continuity_status` show missing vectors?
- Is the query too short or ambiguous?

Tune the smallest relevant setting, then re-run the same debug query.
