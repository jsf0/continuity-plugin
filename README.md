# Hermes Continuity Memory

Local-first structured continuity memory provider for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

This plugin is intended to make Hermes feel more continuous without bloating the active prompt:

- store rich long-term context externally;
- retrieve only compact relevant summaries per turn;
- keep source references for deeper verification;
- remain installable as a plugin instead of requiring a Hermes fork.

## Status

Phase 0/1 scaffold: specification, fixtures, tests, and no-op provider skeleton.

## Install target

Hermes discovers user-installed memory providers under:

```text
$HERMES_HOME/plugins/<provider-name>/
```

This plugin installs to:

```text
$HERMES_HOME/plugins/continuity/
```

Enable it with:

```yaml
memory:
  provider: continuity
```

## Architecture

The plugin implements Hermes' `MemoryProvider` API under provider name `continuity`.

Initial MVP behavior:

- `continuity_status` tool;
- safe local initialization under `$HERMES_HOME/continuity/`;
- no automatic context injection until structured store/retrieval phases are implemented.

Planned behavior:

- SQLite + FTS5 structured `ContextRecord` store;
- budgeted `prefetch(query)` recall;
- session-end consolidation;
- project capsules;
- optional vector/hybrid retrieval.

See [`docs/SPEC.md`](docs/SPEC.md) for the full implementation spec.

## Development

```bash
python -m pytest tests/ -q
python -m ruff check .
```

## Safety model

Retrieved continuity memories are informational background data, not instructions. The plugin must keep automatic prefetch output compact and source-linked.
