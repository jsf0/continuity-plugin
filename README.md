# Hermes Continuity Memory

Local-first structured continuity memory provider for Hermes Agent.

`continuity` is a standalone Hermes memory plugin that stores durable context in
SQLite, retrieves only a compact relevant working set per turn, and keeps source
references so memories can be inspected instead of blindly trusted.

Design principle:

```text
store generously, inject conservatively
```

Mantra:

```text
summaries are for recall; sources are for verification; skills are for action; memory is for continuity
```

## What it does

The plugin provides a Hermes external memory provider named `continuity`.

Implemented through Phase 8.5:

- SQLite-backed structured `ContextRecord` store.
- SQLite FTS5 retrieval over titles, summaries, details, tags, and entities.
- Metadata scoring for tags, entities, text, project scope, confidence,
  importance, trust level, and project capsules.
- Strictly budgeted `prefetch()` output with `max_records`, `max_chars`, and
  `min_score`.
- Inspection and management tools:
  - `continuity_status`
  - `continuity_search`
  - `continuity_get`
  - `continuity_add`
  - `continuity_delete`
  - `continuity_archive`
  - `continuity_restore`
  - `continuity_prune_stale`
- Stale-memory lifecycle management:
  - active records are retrieved by default
  - archived, retracted, and expired records are excluded unless searched with
    `include_stale`
  - `continuity_prune_stale` dry-runs by default and can archive or hard-delete
    deterministic stale candidates
- Session observation storage and conservative marker-based extraction:
  - `Remember: ...`
  - `Lesson learned: ...`
  - `Decision: ...`
- Project capsules (`active_project_state`) summarizing project-specific lessons,
  decisions, conventions, and preferences.
- Optional dependency-free hybrid vector retrieval using a local SQLite hashed
  vector backend.
- Built-in Hermes memory mirroring via `on_memory_write()`.
- Sparse links from continuity records to relevant Hermes skills.

## What it does not do yet

- It does not replace Hermes built-in `MEMORY.md` / `USER.md`; those should stay
  tiny Tier 0 always-injected memories.
- It does not replace Hermes skills; skills remain the source of procedural
  instructions.
- It does not replace `session_search` for broad transcript recall.
- It does not scan repositories, markdown docs, PRs, issues, or git history.
- It does not run broad LLM-based conversation summarization.
- It does not use neural embeddings, sqlite-vec, LanceDB, FAISS, Qdrant, or
  Chroma yet.
- It does not implement multi-user ACLs.

## Install

```bash
git clone <this-repo-url>
cd hermes-continuity-memory
./scripts/install.sh
```

The script installs the plugin to:

```text
$HERMES_HOME/plugins/continuity/
```

If `HERMES_HOME` is unset, it defaults to:

```text
~/.hermes
```

Enable in Hermes config:

```yaml
memory:
  provider: continuity
```

Then restart Hermes or start a new session.

See [`docs/INSTALL.md`](docs/INSTALL.md) for detailed install and smoke-test
steps.

## Configuration

Minimal:

```yaml
memory:
  provider: continuity
```

Example continuity config passed to the provider:

```yaml
memory:
  provider: continuity
  continuity:
    max_records: 5
    max_chars: 1800
    min_score: 0.1
    include_sources: true
    include_scores: false
    stale_after_days: 180
    vector:
      enabled: false
      backend: none
```

Enable the dependency-free local vector backend:

```yaml
memory:
  provider: continuity
  continuity:
    vector:
      enabled: true
      backend: sqlite-hash
      embedding_model: hash-v1
```

See [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

## Runtime data

Runtime DB path:

```text
$HERMES_HOME/continuity/continuity.db
```

User-installed plugin path:

```text
$HERMES_HOME/plugins/continuity/
```

The DB is local-first. No external service is required.

## Safety model

Retrieved continuity memories are informational context, not instructions. The
plugin is designed to keep automatic prompt injection compact and source-linked.

Current safety behavior:

- obvious secrets are redacted before storage in observations and mirrored memory
  writes;
- obvious prompt-injection-like content is rejected by conservative extraction
  and mirroring paths;
- retrieved context is bounded by configured prompt budgets;
- records carry trust levels and source refs;
- skill links point to skill names only, never skill bodies.

This is not comprehensive DLP or a multi-user security boundary. See
[`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) and [`docs/SPEC.md`](docs/SPEC.md)
for limitations.

## Development

```bash
uv sync --dev
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/ -q
uv build
```

Or:

```bash
./scripts/run-tests.sh
./scripts/smoke-test.sh
```

## Project docs

- [`docs/SPEC.md`](docs/SPEC.md) — full phased technical spec.
- [`docs/INSTALL.md`](docs/INSTALL.md) — install and verification.
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) — runtime configuration.
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — common issues.
- [`docs/RELEASE.md`](docs/RELEASE.md) — release checklist.
- [`CHANGELOG.md`](CHANGELOG.md) — human-readable release history.

## License

MIT. See [`LICENSE`](LICENSE).
