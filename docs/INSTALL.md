# Installation

## Prerequisites

- Hermes Agent installed locally.
- Python 3.11+.
- `bash` for helper scripts.
- `uv` for development/test commands.

The plugin itself has no runtime Python dependencies beyond the standard library.

## Install into Hermes

From a checkout of this repository:

```bash
./scripts/install.sh
```

By default, this installs to:

```text
~/.hermes/plugins/continuity/
```

To install into a different Hermes home:

```bash
HERMES_HOME=/path/to/hermes-home ./scripts/install.sh
```

Preview without writing:

```bash
./scripts/install.sh --dry-run
```

## Enable the provider

Edit your main Hermes config, usually:

```bash
$EDITOR ~/.hermes/config.yaml
```

Add or update the `memory` block:

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

The installer deliberately does **not** edit this file. Then restart Hermes or start a new session.

## Verify installation

Run the repository smoke test:

```bash
./scripts/smoke-test.sh
```

The script:

1. Creates a temporary `HERMES_HOME`.
2. Installs the plugin there.
3. Loads the provider directly, or through Hermes' plugin loader when Hermes is
   available under `~/.hermes/hermes-agent`.
4. Initializes the provider.
5. Adds, gets, searches, prefetches, and deletes a record.
6. Verifies skill-link prefetch behavior.
7. Verifies mirrored built-in memory writes.
8. Builds a wheel with `uv` when available and checks `plugin.yaml` / `py.typed` packaging.

Expected output ends with:

```text
smoke test ok
```

## Try the synthetic retrieval demo

To verify retrieval, lifecycle operations, and report-only dream maintenance without waiting to build up real memories, run:

```bash
python scripts/demo-retrieval.py
# or, with uv if available:
./scripts/demo-retrieval.sh
```

The demo uses only synthetic public records in `examples/demo_memory/`. It creates a temporary `HERMES_HOME`, loads `records.jsonl`, runs query expectations from `queries.jsonl`, exercises add/search/archive/restore/delete, runs a report-only dream cycle, and removes the temporary DB when done.

Expected output ends with:

```text
demo retrieval ok
```

## Uninstall

Remove the installed plugin directory:

```bash
rm -rf "$HERMES_HOME/plugins/continuity"
```

This does not remove runtime memory data. To remove the continuity DB too:

```bash
rm -rf "$HERMES_HOME/continuity"
```

Be careful: deleting `$HERMES_HOME/continuity` removes stored continuity memory.
