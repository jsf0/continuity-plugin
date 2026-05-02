# Phase 8 — packaging, documentation, and release polish

Phase 8 turns the working local plugin into a publishable standalone GitHub
project.

## Implemented

- Rewrote `README.md` for current Phase 7.6 behavior.
- Added `LICENSE` using MIT.
- Added `CHANGELOG.md` with initial `0.1.0` unreleased notes.
- Added documentation:
  - `docs/INSTALL.md`
  - `docs/CONFIGURATION.md`
  - `docs/TROUBLESHOOTING.md`
  - `docs/RELEASE.md`
- Added GitHub Actions CI workflow.
- Improved install/test scripts.
- Added `scripts/smoke-test.sh` for clean temp-home verification.
- Added `continuity/py.typed` and package metadata cleanup.

## Verification target

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/ -q
./scripts/smoke-test.sh
uv build
```

## Remaining release choices

Before pushing publicly, decide:

- GitHub repository owner/name.
- Whether MIT remains the desired license.
- Whether to tag `v0.1.0` immediately or keep alpha work unreleased until after
  one real Hermes dogfood install.
