# Phase 6 Notes

## Completed

- Added project capsule construction in `continuity.project`:
  - deterministic capsule id from project id
  - `active_project_state` record kind
  - project identity line
  - Known pitfalls section from `lesson_learned`
  - User decisions section from `decision`
  - Verification section from `project_convention`
  - User preferences section from `user_preference`
  - deduped summaries
  - source refs back to constituent memory records

- Wired `ContinuityProvider.on_session_end()` to update the current project capsule after extracted records are upserted.

- Added capsule retrieval preference:
  - matching project capsules receive an additional scope bonus
  - capsules rank above individual records for project overview / known-pitfall queries

- Updated provider status phase marker to `phase-6-project-capsules`.

## Verification

```text
uv run pytest tests/ -q  ✅ 49 passed
uv run ruff check .      ✅
```

## Intentional boundaries

- Capsules are generated from structured records only; they do not scan repo files yet.
- Capsule sections are conservative and template-based.
- Vector retrieval remains Phase 7.
