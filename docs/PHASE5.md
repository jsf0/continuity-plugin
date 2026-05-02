# Phase 5 Notes

## Completed

- Added `continuity.security` with:
  - basic prompt-injection detection
  - obvious secret detection
  - secret redaction
  - observation truncation

- Added session observation storage to `ContinuityStore`:
  - `add_session_observation()`
  - `list_unconsolidated_observations()`
  - `mark_session_observations_consolidated()`

- Added `continuity.extraction` with conservative heuristic extraction for explicit markers:
  - `Remember: ...` → `user_preference` when preference-like
  - `Lesson learned: ...` → `lesson_learned`
  - `Decision: ...` → `decision`

- Wired provider lifecycle:
  - `sync_turn()` stores redacted/truncated observations
  - `on_session_end()` extracts durable records, upserts deterministic IDs, and marks observations consolidated

- Added dedupe by deterministic record id derived from kind, project scope, and normalized summary.

## Verification

```text
uv run ruff check .      ✅
uv run pytest tests/ -q  ✅ 46 passed
```

## Intentional boundaries

- Extraction is deliberately conservative and marker-based; no LLM extraction yet.
- Full security scanning remains a future hardening area.
- Project capsules remain Phase 6.
- Vector retrieval remains Phase 7.
