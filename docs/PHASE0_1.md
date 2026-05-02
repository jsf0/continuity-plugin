# Phase 0/1 Notes

## Phase 0 completed

- Full implementation spec copied to `docs/SPEC.md`.
- README defines plugin goals, install target, and architecture.
- Eval fixtures exist under `tests/fixtures/continuity_memory/`.
- Tests were written before the provider implementation and initially failed with `ModuleNotFoundError: No module named 'continuity'`.

## Phase 1 completed

- `continuity.ContinuityProvider` exists.
- `register(ctx)` registers the provider.
- `initialize()` creates `$HERMES_HOME/continuity/`.
- `continuity_status` tool returns JSON status.
- Automatic `prefetch()` is intentionally no-op until retrieval phases.
