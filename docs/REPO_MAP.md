# Repository map

This guide points new readers to the important files in the repository.

## Top level

```text
README.md                 project overview, quick start, and doc links
CHANGELOG.md              release history
CONTRIBUTING.md           contributor workflow
SECURITY.md               security reporting and security model
LICENSE                   MIT license
pyproject.toml            package metadata, scripts, dev dependencies, ruff/pytest config
plugin.yaml               Hermes plugin metadata
uv.lock                   locked development dependency graph
.github/workflows/ci.yml  GitHub Actions release gate
```

## Runtime package: `continuity/`

```text
continuity/__init__.py
```

Hermes provider entrypoint. Defines `ContinuityProvider`, provider hooks, prefetch formatting, system-prompt guidance, tool dispatch, and plugin registration.

```text
continuity/config.py
```

Runtime config dataclasses, defaults, parsing, clamping, and accepted backend names.

```text
continuity/models.py
```

Data models, including `ContextRecord`, source references, skill links, and serialization helpers.

```text
continuity/store.py
```

SQLite persistence layer: schema migrations, record CRUD, FTS, source corpus storage, vector rows, association edges, retrieval-event logs, and provider state.

```text
continuity/retrieval.py
```

Main retrieval engine: FTS candidates, metadata scoring, vector blending, reranking, association-graph activation, rejection reasons, and retrieval-gate behavior.

```text
continuity/tools.py
```

Hermes tool schemas and handlers for `continuity_status`, search/get/hydrate/add/delete/archive/restore/debug/dream/quality tools.

```text
continuity/security.py
```

Conservative redaction and prompt-injection checks used by supported write paths.

```text
continuity/memory_mirror.py
```

Logic for turning built-in Hermes memory writes into structured continuity records.

```text
continuity/extraction.py
```

Marker-based session extraction for phrases such as `Remember:`, `Lesson learned:`, and `Decision:`.

```text
continuity/project.py
```

Project/repository detection and project capsule support.

```text
continuity/association.py
```

Association graph helpers for linking related records.

```text
continuity/embeddings.py
```

Vector backend abstraction and implementations, including dependency-free hashed vectors.

```text
continuity/reranking.py
```

Optional local reranker backend support.

```text
continuity/staleness.py
continuity/dream.py
```

Conservative stale-record detection and report/archive maintenance cycles.

```text
continuity/record_quality.py
continuity/quality_backfill.py
```

Record quality checks and quality-report/backfill helpers.

```text
continuity/facets.py
continuity/context_labels.py
continuity/dynamic_expansion.py
continuity/vocabulary.py
continuity/metadata_extraction.py
```

Retrieval-support modules for facets, corpus context labels, query expansion, vocabulary, and metadata extraction.

## Corpus ingestion: `continuity/ingest/`

```text
continuity/ingest/cli.py          CLI entrypoint for continuity-ingest
continuity/ingest/connectors.py   local source discovery
continuity/ingest/parsers.py      text/markdown/manpage parsing
continuity/ingest/segmenters.py   source segmentation
continuity/ingest/extractors.py   deterministic candidate extraction
continuity/ingest/llm_extractors.py optional explicit LLM extraction support
continuity/ingest/quality.py      ingestion quality gates
continuity/ingest/dedupe.py       candidate merge/dedupe logic
continuity/ingest/review.py       review artifact handling
continuity/ingest/importer.py     explicit import into continuity.db
continuity/ingest/refresh.py      changed-source refresh flow
continuity/ingest/eval.py         retrieval evaluation helpers
continuity/ingest/reports.py      review/import report generation
continuity/ingest/validation.py   temporary import/eval validation
continuity/ingest/scripts/        helper entrypoints
```

See `docs/CORPUS_INGESTION.md` for the safe review-first workflow.

## Scripts

```text
scripts/install.sh
```

Copies the plugin package into `${HERMES_HOME:-$HOME/.hermes}/plugins/continuity`. It intentionally does not edit the user's main Hermes config.

```text
scripts/smoke-test.sh
```

Creates a temporary Hermes home, installs the plugin, exercises provider load/add/search/prefetch/delete, checks memory mirroring and skill links, and verifies package metadata when `uv` is available.

```text
scripts/demo-retrieval.py
scripts/demo-retrieval.sh
```

Runs the synthetic public demo corpus in a temporary home and verifies expected retrieval/lifecycle behavior.

```text
scripts/demo-small-model-context.py
```

Prints a reproducible before/after context demonstration showing the compact memory block a small model would receive.

```text
scripts/report-record-quality.py
```

Reports record-quality warnings for an existing continuity database.

## Examples

```text
examples/demo_memory/records.jsonl
examples/demo_memory/queries.jsonl
examples/demo_memory/README.md
```

Synthetic, public demo records and expected retrieval queries. These fixtures are intentionally not real user memory.

## Tests

```text
tests/test_provider_phase*.py       provider lifecycle and phase behavior
tests/test_tools_*.py               tool schemas and handlers
tests/test_retrieval*.py            retrieval ranking, gates, regressions, labels
tests/test_store.py                 SQLite persistence
tests/test_config.py                config parsing and defaults
tests/test_memory_mirror*.py        built-in memory mirroring
tests/test_staleness*.py            stale/archive lifecycle
tests/test_dream*.py                maintenance cycle
tests/test_record_quality*.py       quality reports/backfill
tests/ingest/                       corpus ingestion tests
```

Run the full suite:

```bash
uv run pytest tests/ -q
```

## If you want to change...

| Goal | Start here | Also update |
| --- | --- | --- |
| Retrieval ranking or rejection reasons | `continuity/retrieval.py` | retrieval tests, `docs/TUNING.md` |
| Config defaults or accepted values | `continuity/config.py` | `docs/CONFIGURATION.md`, `docs/TUNING.md`, config tests |
| A continuity tool | `continuity/tools.py`, `continuity/__init__.py` | tool tests, README/tool docs |
| Database schema | `continuity/store.py` | migration tests, smoke test |
| Built-in memory mirroring | `continuity/memory_mirror.py` | mirror tests, safety docs |
| Corpus ingestion | `continuity/ingest/` | ingestion tests, `docs/CORPUS_INGESTION.md` |
| Install flow | `scripts/install.sh` | `docs/INSTALL.md`, smoke test |
| Public demos | `examples/demo_memory/`, `scripts/demo-*` | demo tests, `docs/DEMO.md` |
| Release gate | `.github/workflows/ci.yml`, `docs/RELEASE.md` | local gate commands |

## Development checks

Before opening a PR or publishing a release, run:

```bash
uv sync --dev
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/ -q
uv run python -m compileall continuity tests scripts
./scripts/demo-retrieval.sh --quiet
uv run python scripts/demo-small-model-context.py
./scripts/smoke-test.sh
uv build
```
