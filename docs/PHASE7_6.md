# Phase 7.6 — skill links

Phase 7.6 connects continuity memories to relevant Hermes skills without copying
skill contents into the continuity database.

## Implemented

- Added `SkillLink` model in `continuity.models`.
- Added SQLite schema version 3 with `context_record_skill_links`.
- Added store methods:
  - `upsert_skill_link()`
  - `delete_skill_link()`
  - `list_skill_links(record_id)`
  - `replace_skill_links(record_id, links)`
- Extended `continuity_add` to accept optional `skill_links`.
- Extended `continuity_get` to return `skill_links`.
- Extended `continuity_search` results to return `skill_links`.
- Extended prefetch formatting with compact `Related skills:` hints.
- Record deletion explicitly removes skill links.

## Schema

```sql
CREATE TABLE IF NOT EXISTS context_record_skill_links (
  record_id TEXT NOT NULL,
  skill_name TEXT NOT NULL,
  reason TEXT,
  confidence REAL NOT NULL DEFAULT 0.5,
  source TEXT NOT NULL DEFAULT 'agent_observed',
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  PRIMARY KEY(record_id, skill_name),
  FOREIGN KEY(record_id) REFERENCES context_records(id) ON DELETE CASCADE
);
```

The plugin also explicitly deletes skill links in `delete_record()` so behavior does
not rely only on SQLite foreign-key cascade settings.

## Tool shape

`continuity_add` can now include:

```json
{
  "kind": "lesson_learned",
  "title": "OpenBSD Rust lint gotcha",
  "summary": "patch lint can falsely report Rust 2015 async errors; verify with cargo check.",
  "skill_links": [
    {
      "skill_name": "devops/openbsd-rust-dev-loop",
      "reason": "Relevant for OpenBSD Rust verification.",
      "confidence": 0.95,
      "source": "explicit_user"
    }
  ]
}
```

Responses from `continuity_add`, `continuity_get`, and `continuity_search` include
`skill_links`.

## Prefetch behavior

When a selected memory has skill links, prefetch can include a compact hint:

```text
Related skills: devops/openbsd-rust-dev-loop
```

Only the strongest skill link is shown per memory for now. This keeps prompt use
small and avoids turning related skills into instructions. The skill itself is not
loaded automatically and its content is not stored in continuity.

## Non-goals

- No skill body duplication in SQLite.
- No automatic skill loading from the memory provider.
- No broad memory-to-memory graph.
- No persisted weak embedding-similarity links.

## Verification

```bash
uv run pytest tests/test_skill_links_phase7_6.py -q
uv run ruff format .
uv run ruff check .
uv run pytest tests/ -q
```
