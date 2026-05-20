# Operations guide

This guide covers day-to-day operation after the plugin is installed.

## Runtime locations

Plugin code:

```text
${HERMES_HOME:-$HOME/.hermes}/plugins/continuity/
```

Runtime data:

```text
${HERMES_HOME:-$HOME/.hermes}/continuity/continuity.db
```

The database is local SQLite. The plugin does not encrypt it.

## Inspect provider status

Use:

```text
continuity_status
```

Useful fields include:

- `initialized` — whether Hermes initialized the provider.
- `record_count` — number of stored records.
- `db_path` — SQLite path in use.
- `current_project_display_name` — detected project scope.
- `vector_enabled`, `vector_available`, `vector_count`, `records_missing_vectors`.
- `reranker_enabled`, `reranker_available`.
- `retrieval_gates` — live effective gate settings.
- `pinned_system_prompt_enabled` and pinned memory settings.
- `dream_enabled` and `dream_last_run_at`.

## Add explicit memory

Use `continuity_add` for structured records. Keep summaries compact and durable.

Example shape:

```json
{
  "kind": "decision",
  "title": "Demo dashboard API framework",
  "summary": "The demo-dashboard project should use FastAPI for its small Python API.",
  "scope_project": "demo-dashboard",
  "tags": ["demo-dashboard", "api"],
  "entities": ["FastAPI"],
  "confidence": 0.9,
  "importance": 0.7
}
```

Do not store secrets, credentials, regulated data, or raw logs.

## Search memory manually

Use:

```text
continuity_search(query="what API framework should demo-dashboard use?", limit=5)
```

Manual search answers “is a matching record in the store?” It does not prove the provider would inject that record for every turn.

## Debug automatic retrieval

Use:

```text
continuity_debug_retrieval(query="the exact user wording", limit=5)
```

Debug retrieval explains:

- first-stage candidates;
- scores and score components;
- selected records;
- rejected candidates and rejection reasons;
- graph activation behavior;
- stale/lifecycle filtering;
- tuning advice for relevant gates.

Use this before changing tuning settings.

## Hydrate corpus-backed records

If a record cites source corpus segments, use:

```text
continuity_hydrate(id="record_id")
```

Hydration returns the continuity record plus source text snippets when available. Use it before quoting or relying on detailed source claims.

## Archive, restore, and delete

Prefer archiving over deleting for ordinary stale records:

```text
continuity_archive(id="record_id", reason="superseded by newer project state")
continuity_restore(id="record_id")
```

Hard delete only when the record is clearly wrong, sensitive, or should not exist:

```text
continuity_delete(id="record_id")
```

Normal retrieval excludes archived, retracted, and expired records by default.

## Stale-memory maintenance

Start with a dry run:

```text
continuity_prune_stale(dry_run=true)
```

If the candidates look safe, archive rather than delete:

```text
continuity_prune_stale(dry_run=false, mode="archive")
```

The provider also exposes a maintenance cycle:

```text
continuity_dream(mode="report")
```

Safer modes:

- `report` — inspect only.
- `archive-safe` — archive conservative candidates.
- `archive-all-candidates` — more aggressive; use with care.

## Vector maintenance

If you enable vector retrieval after records already exist, reindex:

```text
continuity_reindex_vectors
```

Then inspect:

```text
continuity_status
```

Look for:

```json
{
  "vector_enabled": true,
  "vector_available": true,
  "records_missing_vectors": 0
}
```

If vectors are unavailable, confirm the configured backend and optional dependencies.

## Quality warnings

Use:

```text
continuity_quality_report
```

This reports quality warnings such as weak summaries, questionable metadata, or records that may need review. Quality reports are advisory; inspect before mutating records.

## Backup

To back up the continuity database:

```bash
cp "${HERMES_HOME:-$HOME/.hermes}/continuity/continuity.db" continuity.db.backup
```

For a more careful SQLite backup while a process might be active, use the SQLite shell if available:

```bash
sqlite3 "${HERMES_HOME:-$HOME/.hermes}/continuity/continuity.db" ".backup continuity.db.backup"
```

## Restore

Stop Hermes or start from a session where the provider is not actively writing, then copy the backup back into place:

```bash
cp continuity.db.backup "${HERMES_HOME:-$HOME/.hermes}/continuity/continuity.db"
```

Restart Hermes or start a new session.

## Wipe all continuity data

Warning: this removes stored continuity memory.

```bash
rm -rf "${HERMES_HOME:-$HOME/.hermes}/continuity"
```

This does not uninstall the plugin code.

## Upgrade plugin code

From the repository root:

```bash
git pull
./scripts/install.sh
```

Then restart Hermes or start a new session.

The installer copies code only. It does not edit your Hermes config and does not remove the runtime database.

## Roll back plugin code

Check out a previous commit or tag and reinstall:

```bash
git checkout <previous-tag-or-commit>
./scripts/install.sh
```

Restart Hermes or start a new session.

Keep database backups before rolling across schema changes.

## Suggested maintenance cadence

For normal local use:

- occasionally run `continuity_status` to confirm provider/vector health;
- use `continuity_debug_retrieval` when a memory surprises you;
- run `continuity_prune_stale(dry_run=true)` before large cleanup;
- archive stale records before deleting them;
- back up `continuity.db` before upgrades or bulk imports;
- keep real memory databases out of public repositories.
