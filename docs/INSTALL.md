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

Set Hermes memory provider to `continuity`:

```yaml
memory:
  provider: continuity
```

Then restart Hermes or start a new session.

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
