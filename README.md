# Hermes Continuity Memory

Scalable contextual recall for Hermes Agent — without stuffing every memory into the prompt.

Hermes Continuity Memory is a local-first structured memory provider for Hermes Agent. In the recommended production setup, it replaces Hermes' stock built-in memory as the primary memory provider: a tiny Tier 0 set of high-trust continuity records is pinned into the system prompt, while the long tail of project state, decisions, debugging lessons, environment facts, and preferences stays in SQLite and is retrieved only when relevant.

## Rationale

The stock Hermes memory system uses MEMORY.md for important memories, but tries to keep it small to avoid putting too much information into prompts. This works well for highly curated memories, but necessarily limits the amount that can be stored.

Continuity Memory uses a SQLite database and a retrieval mechanism that is designed to only return the relevant memories for each conversation. This allows a much larger set of memories to be stored, and only relevant ones added to prompts, so that the model gets highly accurate, scoped memories relevant to the conversation or task.

This retrieval mechanism models memories as nodes in an association graph, with stronger or weaker ties between individual memories, based on Collins and Loftus' 1975 paper ["A spreading-activation theory of semantic processing"](https://psycnet.apa.org/doiLanding?doi=10.1037%2F0033-295X.82.6.407) . This means Continuity is capable of fuzzy searches and returns multiple related memories even if there is no exact match.

This is definitely alpha at this point, and is under active testing and development. It will have some rough edges.

## Highlights

- **Local SQLite store** for durable `ContextRecord` memories.
- **Hybrid retrieval** using SQLite FTS5, metadata scoring, optional vectors, optional reranking, and optional association-graph expansion.
- **Explainable debug tools** for status, search, exact get, retrieval diagnostics, graph inspection, and stale-memory lifecycle operations.
- **Budgeted prompt injection** via Hermes memory-provider prefetch, with retrieved records treated as informational background rather than instructions.
- **Built-in memory migration/mirroring** through `on_memory_write()` for compatibility, with semantic record titles instead of generic mirror labels.
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

- a second always-on prompt dump; Tier 0 pinned continuity records should stay tiny, high-trust, and auditable;
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
- Built-in Hermes memory migration/mirroring via `on_memory_write()` with semantic titles.
- Pinned system-prompt Tier 0 records, enabled by default, plus always-on compact provider guidance.

## Requirements

- Hermes Agent installed locally.
- Python 3.11+.
- `bash` for the install/uninstall helper scripts.

The default runtime path is dependency-free: SQLite/FTS, hashed vectors, association graph retrieval, and all Hermes tools use only the Python standard library. `uv`, `pytest`, `ruff`, `sentence-transformers`, and `torch` are needed only for development checks or optional neural embeddings/reranking.

## Install

The public repository is `jsf0/continuity-plugin`:

```bash
git clone https://github.com/jsf0/continuity-plugin.git
cd continuity-plugin
./scripts/install.sh
```

To install into a non-default Hermes home:

```bash
HERMES_HOME=/path/to/hermes-home ./scripts/install.sh
```

To preview without writing files:

```bash
./scripts/install.sh --dry-run
```

The installer copies the plugin package to:

```text
${HERMES_HOME:-$HOME/.hermes}/plugins/continuity/
```

It deliberately does **not** edit your Hermes config and does **not** delete or migrate any memory database. Runtime data is stored separately at:

```text
${HERMES_HOME:-$HOME/.hermes}/continuity/continuity.db
```

## Enable the provider

Edit your main Hermes config, usually `~/.hermes/config.yaml`, and start with the minimal config:

```yaml
memory:
  provider: continuity
```

That is enough for a first install. The built-in defaults enable conservative retrieval, provider guidance, association-graph search, and a tiny Tier 0 pinned-memory prompt. Optional vector retrieval is **off** unless you enable it.

Recommended dependency-free config if you want local hashed vectors enabled immediately:

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
    pinned_system_prompt:
      enabled: true
      include_records: true
      max_chars: 1200
      max_records: 5
      kinds: [user_preference, project_convention]
      min_importance: 0.75
```

After updating config, restart Hermes or start a new session. Then ask Hermes to run:

```text
continuity_status
```

A healthy install reports `provider: continuity`, `initialized: true`, a `db_path` under your Hermes home, and the available continuity tools.

## Quick verification from a checkout

Before changing your real Hermes config, you can run the isolated smoke test:

```bash
./scripts/smoke-test.sh
```

Expected final line:

```text
smoke test ok
```

The smoke test creates a temporary `HERMES_HOME`, installs the plugin there, loads the provider, exercises add/search/prefetch/delete, verifies memory mirroring and skill-link output, and checks packaging metadata. It does not read or modify your real `~/.hermes/continuity/continuity.db`.

## Optional neural embeddings and reranking

Use the dependency-free install first unless you specifically need neural retrieval. To experiment with local `sentence-transformers` vectors/reranking in a development checkout:

```bash
uv sync --extra embeddings --dev
```

Then configure:

```yaml
memory:
  provider: continuity
  continuity:
    vector:
      enabled: true
      backend: sentence-transformers
      embedding_model: BAAI/bge-small-en-v1.5
    reranker:
      enabled: true
      backend: sentence-transformers
      model: BAAI/bge-reranker-base
      min_score: 0.15
```

See [`docs/INSTALL.md`](docs/INSTALL.md) for detailed install, upgrade, rollback, uninstall, and troubleshooting steps. See [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for all configuration options.

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

For orientation, start with [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/REPO_MAP.md`](docs/REPO_MAP.md).

To try retrieval without using your real memory DB, run the public synthetic demo corpus:

```bash
python scripts/demo-retrieval.py
# or, with uv if available:
./scripts/demo-retrieval.sh

# Show the exact compact memory block a small model would receive
# for a synthetic before/after continuity prompt:
python scripts/demo-small-model-context.py
```

The demo creates a temporary `HERMES_HOME`, loads `examples/demo_memory/records.jsonl`, runs query expectations from `examples/demo_memory/queries.jsonl`, exercises add/search/archive/restore/delete, and runs a report-only dream cycle. No real user memories are included.

`demo-small-model-context.py` is not a model benchmark and does not call an LLM. It is a reproducible prompt-context demonstration: the same synthetic question has zero project memory without continuity and one compact retrieved record with continuity, showing the bounded context that a smaller model would see before answering.

### Demo retrieval uses your current checkout

The demo imports `continuity` from the repository directory you are running it from, not from an already-installed Hermes plugin copy. That makes it useful as a fast local regression harness while developing:

```bash
# edit continuity/retrieval.py, continuity/store.py, etc.
python scripts/demo-retrieval.py
```

If you change retrieval, lifecycle, or dream-maintenance code, the demo runs against those uncommitted local changes. It also creates a temporary SQLite DB, so it does not read or modify your real continuity memory database under `~/.hermes/continuity/`.

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

- [`docs/INSTALL.md`](docs/INSTALL.md) — install, verify, upgrade, rollback, and uninstall.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system design, data flow, storage, retrieval, and safety model.
- [`docs/REPO_MAP.md`](docs/REPO_MAP.md) — where to find the main code, tests, scripts, and extension points.
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) — complete runtime configuration reference.
- [`docs/TUNING.md`](docs/TUNING.md) — plain-English retrieval knobs, symptoms, and example recipes.
- [`docs/DEMO.md`](docs/DEMO.md) — walkthrough for the synthetic public demo corpus and small-model context demo.
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md) — day-to-day status, search, debug, archive, backup, and maintenance workflows.
- [`docs/PRIVACY.md`](docs/PRIVACY.md) — what is stored, where it lives, prompt exposure, deletion, and public-release hygiene.
- [`docs/CORPUS_INGESTION.md`](docs/CORPUS_INGESTION.md) — review-first corpus ingestion, temporary validation, and scale/debug stats.
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — common issues and debugging.
- [`docs/SPEC.md`](docs/SPEC.md) — phased technical spec.
- [`docs/RELEASE.md`](docs/RELEASE.md) — release checklist.
- [`CHANGELOG.md`](CHANGELOG.md) — release history.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — development workflow.
- [`SECURITY.md`](SECURITY.md) — security reporting and supported versions.

## License

MIT. See [`LICENSE`](LICENSE).
