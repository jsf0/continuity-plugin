# Phase 8.5 — stale memory lifecycle

Phase 8.5 adds a safe way to remove stale continuity memories from normal
retrieval without immediately destroying audit/debug history.

## Implemented

- Extended `ContextRecord` with stale lifecycle fields:
  - `status`: `active`, `archived`, or `retracted`
  - `superseded_by`
  - `stale_reason`
  - `archived_at`
- Bumped the SQLite schema to version 4 and added idempotent migration for the
  new columns.
- Retrieval now excludes non-active records and expired records by default.
- `continuity_search` accepts `include_stale: true` for inspection/debugging.
- Added management tools:
  - `continuity_archive`
  - `continuity_restore`
  - `continuity_prune_stale`
- `continuity_prune_stale` dry-runs by default and reports deterministic
  candidate reasons before mutating records.
- Supported prune modes:
  - `archive` — default; removes candidates from normal retrieval but keeps them
    in the DB.
  - `delete` — hard-deletes candidates and associated FTS/vector/skill-link rows.

## Current stale candidate rules

The prune pass is intentionally conservative and deterministic:

1. `expires_at` in the past is stale.
2. Older `active_project_state` records for the same project/repo scope are
   superseded by the newest one.
3. Older built-in memory mirrors that are similar to a newer mirror in the same
   source/kind/title/scope bucket are stale candidates.
4. Low-importance non-user-preference records older than `stale_after_days` can
   be candidates if they have not been recently confirmed or accessed.

`explicit_user` and `user_preference` records are not age-pruned by default.

## Operational guidance

Prefer archive over hard delete:

```text
continuity_prune_stale {"dry_run": true}
continuity_prune_stale {"dry_run": false, "mode": "archive"}
```

Use `include_stale: true` during debugging to inspect archived/retracted/expired
records that normal retrieval would skip.

Hard delete remains available for clearly wrong or sensitive records, but should
be explicit.

## Verification target

```bash
uv run pytest tests/test_staleness_phase8_5.py -q
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
./scripts/smoke-test.sh
```
