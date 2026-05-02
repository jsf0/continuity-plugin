# Phase 7.5 — built-in memory write mirroring

Phase 7.5 makes Hermes built-in memory writes a high-signal ingestion path for
continuity memory.

## Implemented

- Added `continuity.memory_mirror` with:
  - deterministic mirror ids from target + normalized sanitized content
  - conservative deterministic classification
  - redaction/truncation before persistence
  - prompt-injection rejection after redaction
  - `built_in_memory` source refs

- Implemented `ContinuityProvider.on_memory_write()`:
  - `add` creates/upserts a mirrored `ContextRecord`
  - `replace` upserts the new content without guessing old content
  - `remove` deletes the deterministic mirrored record for the removed content

- Mirrored records use:
  - `trust_level = built_in_memory_mirror`
  - ids like `mirror_user_<hash>` or `mirror_memory_<hash>`
  - source refs like `built_in_memory:user` or `built_in_memory:memory`

- Vector integration:
  - mirrored records use the provider's normal `_upsert_record()` path
  - vector rows are created when vector mode is enabled
  - vector rows are deleted on mirrored remove

## Classification

No LLM classification is used. Rules are conservative:

- `target=user` → `user_preference`
- `target=memory` containing `lesson`, `gotcha`, `pitfall`, `beware`, `workaround`, or `quirk` → `lesson_learned`
- `target=memory` containing `decided`, `declined`, `chose`, or `decision` → `decision`
- `target=memory` containing project/convention/build/test/verify language while a project is active → `project_convention`
- fallback for `target=memory` → `environment_fact`

Project scope is only attached for `target=memory` writes when the current
project appears relevant. User preference mirrors remain global by default.

## Safety behavior

- Obvious secrets are redacted as `[REDACTED_SECRET]` before storage.
- Obvious prompt-injection-like content is rejected and not mirrored.
- Mirrored content is truncated to a fixed budget before storage.

## Intentional limits

- The plugin does not parse or mirror skill contents.
- Replace cannot delete an old deterministic id unless Hermes passes old content;
  current behavior only upserts the new content.
- Classification is keyword-based and intentionally conservative.
- Project capsules are not force-updated on every memory write; mirrored project
  records naturally participate when capsules are generated.

## Verification

Targeted tests:

```bash
uv run pytest tests/test_memory_mirror_phase7_5.py -q
```

Full gate:

```bash
uv run ruff format .
uv run ruff check .
uv run pytest tests/ -q
```
