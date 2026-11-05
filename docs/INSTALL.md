# Installation, verification, upgrade, and uninstall

This guide installs the continuity memory provider into a local Hermes Agent home. The installer copies plugin code only; it does not edit your Hermes config and does not delete memory data.

## Prerequisites

- Hermes Agent installed locally.
- Python 3.11+.
- `bash` for helper scripts.

The plugin runtime uses only the Python standard library by default. `uv` is useful for development, tests, and package builds, but it is not required for a normal install. Optional neural embeddings/reranking require extra packages.

## Quick install

From a fresh clone:

```bash
git clone https://github.com/jsf0/continuity-plugin.git
cd continuity-plugin
./scripts/install.sh
```

From an existing checkout of this repository:

```bash
./scripts/install.sh
```

By default, this copies the plugin package to:

```text
${HERMES_HOME:-$HOME/.hermes}/plugins/continuity/
```

Install into a different Hermes home:

```bash
HERMES_HOME=/path/to/hermes-home ./scripts/install.sh
```

Preview the copy operation without writing files:

```bash
./scripts/install.sh --dry-run
```

## Enable the provider

Edit your main Hermes config, usually:

```bash
$EDITOR ~/.hermes/config.yaml
```

Minimal config:

```yaml
memory:
  provider: continuity
```

Then enable the plugin itself — the provider setting and the plugin enable
flag are **two independent switches**, and both are required:

```bash
hermes plugins enable continuity
```

> **Do not skip the plugin enable.** `hermes doctor` can report the memory
> provider as active even while the plugin is disabled (a missing
> `plugins: enabled: [continuity]` entry), so the omission fails silently:
> continuity tools never appear and no memory is stored.

Recommended dependency-free first-install config:

```yaml
memory:
  provider: continuity
  continuity:
    max_records: 5
    max_chars: 1800
    min_score: 0.1
    include_sources: true
    include_scores: false

    # Dependency-free local vectors. Good default for first install.
    vector:
      enabled: true
      backend: sqlite-hash

    # Optional: enable only after installing sentence-transformers dependencies.
    reranker:
      enabled: false
      backend: none

    association_graph:
      enabled: true

    # Tier 0 memory: tiny, high-trust continuity records pinned every turn.
    pinned_system_prompt:
      enabled: true
      include_records: true
      max_chars: 1200
      max_records: 5
      kinds: [user_preference, project_convention]
      min_importance: 0.75

    # Optional maintenance cycle. Manual continuity_dream works regardless;
    # scheduled checks run only when Hermes initializes or processes turns.
    dream:
      enabled: false
      schedule: "03:30"
      timezone: "UTC"
      mode: report
```

Then restart Hermes or start a new session.

## Production memory model

This plugin is intended to replace stock Hermes memory as the primary memory provider:

```yaml
memory:
  provider: continuity
```

Existing stock memory can be mirrored or migrated, but avoid keeping a second large always-on memory prompt alongside continuity. Continuity keeps a tiny optional Tier 0 prompt plus per-turn retrieval for the long tail.

## Verify installation

Run the repository smoke test:

```bash
./scripts/smoke-test.sh
```

Expected final line:

```text
smoke test ok
```

The smoke test creates a temporary `HERMES_HOME`, installs the plugin there, loads the provider, exercises add/search/prefetch/delete, verifies memory mirroring and skill-link output, builds a wheel when `uv` is available, and checks package metadata.

## Verify import path manually

After installing, verify Python imports the installed plugin copy rather than the repository checkout:

```bash
cd /tmp
PYTHONPATH="${HERMES_HOME:-$HOME/.hermes}/plugins" python - <<'PY'
import continuity
print(continuity.__file__)
PY
```

Expected path shape:

```text
.../.hermes/plugins/continuity/__init__.py
```

## Try the synthetic retrieval demo

The public demo uses only synthetic JSONL records and a temporary database:

```bash
./scripts/demo-retrieval.sh
```

Quiet mode:

```bash
./scripts/demo-retrieval.sh --quiet
```

Expected final line:

```text
demo retrieval ok
```

Show the compact context block a small model would receive:

```bash
python scripts/demo-small-model-context.py
```

Expected final line:

```text
small model context demo ok
```

See `docs/DEMO.md` for a walkthrough.

## Data locations

Plugin code:

```text
${HERMES_HOME:-$HOME/.hermes}/plugins/continuity/
```

Runtime database:

```text
${HERMES_HOME:-$HOME/.hermes}/continuity/continuity.db
```

Removing plugin code does not remove runtime memory data.

## Upgrade

From the repository root:

```bash
git pull
./scripts/install.sh
```

Restart Hermes or start a new session.

The installer replaces the installed plugin code directory. It does not edit config and does not delete the runtime database.

Before major upgrades, back up the database:

```bash
cp "${HERMES_HOME:-$HOME/.hermes}/continuity/continuity.db" continuity.db.backup
```

## Roll back

Check out a previous tag or commit and reinstall:

```bash
git checkout <previous-tag-or-commit>
./scripts/install.sh
```

Restart Hermes or start a new session. Keep database backups before rolling across schema changes.

## Uninstall plugin code only

Use the helper script:

```bash
./scripts/uninstall.sh
```

Or remove the installed plugin directory manually:

```bash
rm -rf "${HERMES_HOME:-$HOME/.hermes}/plugins/continuity"
```

Then remove or change the `memory.provider: continuity` config block in your Hermes config and restart Hermes.

This does not remove stored continuity memory.

## Wipe continuity memory data

Warning: this deletes stored continuity records, source references, vectors, retrieval logs, and maintenance state.

Use the helper script with an explicit flag:

```bash
./scripts/uninstall.sh --remove-data
```

Or remove the data directory manually:

```bash
rm -rf "${HERMES_HOME:-$HOME/.hermes}/continuity"
```

## Install optional neural embeddings/reranking dependencies

The default install does not require ML dependencies. To experiment with `sentence-transformers` vectors or reranking in a development checkout:

```bash
uv sync --extra embeddings --dev
```

Then configure, for example:

```yaml
memory:
  provider: continuity
  continuity:
    vector:
      enabled: true
      backend: sentence-transformers
      embedding_model: mixedbread-ai/mxbai-embed-large-v1
    reranker:
      enabled: true
      backend: sentence-transformers
      model: BAAI/bge-reranker-base
```

Use `sqlite-hash` first unless you specifically need neural retrieval.

## Troubleshooting quick checks

Check installed files:

```bash
find "${HERMES_HOME:-$HOME/.hermes}/plugins/continuity" -maxdepth 1 -type f | sort
```

Check provider health inside Hermes:

```text
continuity_status
```

If no memories are retrieved:

```text
continuity_search(query="expected memory")
continuity_debug_retrieval(query="exact user wording")
```

See `docs/TROUBLESHOOTING.md` and `docs/TUNING.md` for more detail.
