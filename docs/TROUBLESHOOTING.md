# Troubleshooting

## Provider does not load

Check install location:

```bash
printf '%s\n' "${HERMES_HOME:-$HOME/.hermes}/plugins/continuity"
```

The directory should contain files like:

```text
__init__.py
plugin.yaml
models.py
store.py
```

Reinstall from the repository root:

```bash
./scripts/install.sh
```

Then restart Hermes or start a new session.

## `continuity_status` says provider is not initialized

The provider was discovered but not initialized by Hermes. Confirm Hermes config
selects this provider:

```yaml
memory:
  provider: continuity
```

Start a fresh Hermes session after changing config.

## No memories are retrieved

Common reasons:

- No durable `ContextRecord`s exist yet.
- Query score is below `min_score`.
- Current project scope differs from the record's scope.
- The memory was stored only as a `session_observation`, not a durable record.

Ways to add durable records today:

- `continuity_add`
- explicit session markers:
  - `Remember: ...`
  - `Lesson learned: ...`
  - `Decision: ...`
- Hermes built-in memory writes mirrored through `on_memory_write()`

Inspect manually with:

```text
continuity_status
continuity_search
continuity_get
```

## Prefetch output is too large or too small

Tune:

```yaml
max_records: 5
max_chars: 1800
min_score: 0.1
include_sources: true
include_scores: false
```

For debugging, temporarily set:

```yaml
include_scores: true
```

## Vector mode does not improve recall

The current vector backend is `sqlite-hash`, a deterministic local hashed-vector
backend. It is useful for dependency-free hybrid retrieval tests and some fuzzy
lexical/synonym cases, but it is not equivalent to neural embeddings.

If vector mode is enabled, check status:

```json
{
  "vector_enabled": true,
  "vector_available": true,
  "vector_count": 1
}
```

If `vector_count` is zero, no records have been indexed since vector mode was
enabled. Re-add records or restart the provider so initialization indexes
existing records.

## Skill links are not shown

Skill links are only shown when a retrieved record has associated links.

Add a record with `skill_links`, then search or prefetch it:

```json
{
  "skill_links": [
    {
      "skill_name": "devops/openbsd-rust-dev-loop",
      "reason": "Relevant for OpenBSD Rust verification.",
      "confidence": 0.95
    }
  ]
}
```

Prefetch currently shows only the strongest linked skill per memory to avoid
prompt bloat.

## Secrets in stored content

The plugin redacts obvious secret patterns in observations and mirrored built-in
memory writes. It is not comprehensive DLP.

If sensitive data is accidentally stored, delete the record:

```text
continuity_delete
```

Or remove the database if you intentionally want to wipe all continuity memory:

```bash
rm -rf "${HERMES_HOME:-$HOME/.hermes}/continuity"
```

## Tests fail because `uv` is missing

Install `uv` from Astral, then run:

```bash
uv sync --dev
uv run pytest tests/ -q
```

Without `uv`, use an existing Python 3.11+ environment with `pytest` and `ruff`
installed.
