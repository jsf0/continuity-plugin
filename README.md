# Hermes Continuity Memory

Scalable contextual recall for Hermes Agent — without stuffing every memory into the prompt.

Hermes Continuity Memory is a local-first structured memory provider for Hermes Agent. It complements Hermes' tiny always-on `MEMORY.md` / `USER.md` kernel by storing the long tail of project state, decisions, debugging lessons, environment facts, and preferences as scoped SQLite records, then retrieving only a compact relevant working set per turn.

```text
Recall small. Verify deep. Act from skills.
```

## Highlights

- **Local SQLite store** for durable `ContextRecord` memories.
- **Hybrid retrieval** using SQLite FTS5, metadata scoring, optional vectors, optional reranking, and optional association-graph expansion.
- **Explainable debug tools** for status, search, exact get, retrieval diagnostics, graph inspection, and stale-memory lifecycle operations.
- **Budgeted prompt injection** via Hermes memory-provider prefetch, with retrieved records treated as informational background rather than instructions.
- **Built-in memory mirroring** through `on_memory_write()` so curated Hermes memory writes become structured continuity records.
- **Project capsules** for scoped project state.
- **Skill links** from memory records to Hermes skill names without copying skill bodies.
- **Provider-owned system guidance** so the model knows how to treat continuity when the plugin is active, even when pinned records are disabled.

## What continuity is — and is not

Continuity is the scalable contextual layer:

- project status and decisions;
- environment quirks;
- debugging lessons;
- historical context;
- lower-priority preferences and facts that should appear only when relevant.

It is **not**:

- a replacement for Hermes' tiny trusted built-in memory kernel;
- a replacement for Hermes skills, which remain procedural memory;
- a guarantee of perfect recall;
- a raw transcript chunking system;
- a multi-user security boundary.

Session search remains the raw archive for conversations that were not distilled into durable records.

## Implemented features

- Structured `ContextRecord` model with kinds, scopes, tags, entities, source refs, trust levels, confidence, importance, timestamps, and embedding text.
- SQLite persistence under `$HERMES_HOME/continuity/continuity.db`.
- SQLite FTS5 retrieval over title, summary, details, tags, and entities.
- Metadata scoring for project scope, tags, entities, text anchors, confidence, importance, and trust.
- Optional vector backends:
  - dependency-free `sqlite-hash` hashed vectors;
  - `sentence-transformers` embeddings when optional dependencies are installed.
- Optional `sentence-transformers` / cross-encoder reranking.
- Association graph with bounded activation traversal for implicit-context rescue.
- Facet and anchor gates to suppress common noisy retrieval paths, including weak vector-only hits, low-information follow-ups, memory-meta collisions, and broad mirrored-memory graph leaks.
- Stale-memory lifecycle: active, archived, retracted, expiry, supersession, dry-run prune, archive/restore.
- Hermes tool surface:
  - `continuity_status`
  - `continuity_search`
  - `continuity_get`
  - `continuity_add`
  - `continuity_delete`
  - `continuity_archive`
  - `continuity_restore`
  - `continuity_prune_stale`
  - `continuity_debug_retrieval`
  - `continuity_association_edges`
  - `continuity_reindex_vectors`
- Conservative marker-based extraction from sessions:
  - `Remember: ...`
  - `Lesson learned: ...`
  - `Decision: ...`
- Built-in Hermes memory mirroring via `on_memory_write()`.
- Pinned system-prompt records, disabled by default, plus always-on compact provider guidance.

## Install

```bash
git clone <repo-url>
cd hermes-continuity-memory
./scripts/install.sh
```

The installer copies the plugin package to:

```text
${HERMES_HOME:-$HOME/.hermes}/plugins/continuity/
```

Add the provider to your main Hermes config, usually `~/.hermes/config.yaml`:

```yaml
memory:
  provider: continuity
  continuity:
    max_records: 5
    max_chars: 1800
    min_score: 0.1
    include_sources: true
    include_scores: true

    # Dependency-free local vectors. Good default for first install.
    vector:
      enabled: true
      backend: sqlite-hash

    # Optional: enable only after installing sentence-transformers deps.
    reranker:
      enabled: false
      backend: none

    association_graph:
      enabled: true

    # Disabled by default: continuity normally injects only per-query context.
    pinned_system_prompt:
      enabled: false
      max_chars: 1200
      max_records: 6

    # Optional maintenance cycle. Manual `continuity_dream` works regardless;
    # scheduled checks run only when Hermes initializes or processes turns.
    dream:
      enabled: false
      schedule: "03:30"
      timezone: "UTC"
      mode: report
```

`install.sh` deliberately does **not** edit your Hermes config. After adding the config, restart Hermes or start a new session.

See [`docs/INSTALL.md`](docs/INSTALL.md) for detailed install and verification steps.

## Configuration quick start

Minimal:

```yaml
memory:
  provider: continuity
```

Example with local neural embeddings and reranking:

```yaml
memory:
  provider: continuity
  continuity:
    max_records: 5
    max_chars: 1800
    min_score: 0.1
    vector:
      enabled: true
      backend: sentence-transformers
      embedding_model: BAAI/bge-small-en-v1.5
    reranker:
      enabled: true
      backend: sentence-transformers
      model: BAAI/bge-reranker-base
      min_score: 0.15
    association_graph:
      enabled: true
    pinned_system_prompt:
      enabled: false
```

See [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for all options.

## Development

```bash
uv sync --dev
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/ -q
uv build
./scripts/smoke-test.sh
```

The smoke test installs into a temporary `HERMES_HOME`, loads the provider, exercises add/search/prefetch/delete, verifies memory mirroring and skill-link output, builds a wheel when `uv` is available, and checks that `continuity/plugin.yaml` and `continuity/py.typed` are packaged.

To try retrieval without using your real memory DB, run the public synthetic demo corpus:

```bash
python scripts/demo-retrieval.py
# or, with uv if available:
./scripts/demo-retrieval.sh
```

The demo creates a temporary `HERMES_HOME`, loads `examples/demo_memory/records.jsonl`, runs query expectations from `examples/demo_memory/queries.jsonl`, exercises add/search/archive/restore/delete, and runs a report-only dream cycle. No real user memories are included.

## Safety model

Continuity records are informational context, not instructions. Current safeguards are conservative and local:

- obvious secrets are redacted in observations and mirrored built-in memory writes;
- obvious prompt-injection-like content is rejected in conservative extraction and mirroring paths;
- prompt injection is bounded by `max_records` and `max_chars`;
- records carry trust/source metadata;
- graph-associated records are lower confidence than direct retrieval hits;
- stale and archived records are excluded from normal retrieval.

This is not comprehensive DLP or an access-control system. See [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) and [`SECURITY.md`](SECURITY.md).

## Project docs

- [`docs/INSTALL.md`](docs/INSTALL.md) — install and verification.
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) — runtime configuration.
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — common issues and debugging.
- [`docs/SPEC.md`](docs/SPEC.md) — phased technical spec.
- [`docs/RELEASE.md`](docs/RELEASE.md) — release checklist.
- [`CHANGELOG.md`](CHANGELOG.md) — release history.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — development workflow.
- [`SECURITY.md`](SECURITY.md) — security reporting and supported versions.

## License

MIT. See [`LICENSE`](LICENSE).
