# Release checklist

Use this checklist before tagging a public release.

## 1. Verify working tree

```bash
git status --short
```

Expected: no unrelated changes.

## 2. Run local gate

```bash
uv sync --dev
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/ -q
uv build
```

## 3. Run smoke test

```bash
./scripts/smoke-test.sh
```

Expected output ends with:

```text
smoke test ok
```

## 4. Review docs

Confirm these are current:

- `README.md`
- `CHANGELOG.md`
- `docs/INSTALL.md`
- `docs/CONFIGURATION.md`
- `docs/TROUBLESHOOTING.md`
- `docs/SPEC.md`

## 5. Bump version if needed

Update version in:

```text
pyproject.toml
continuity/plugin.yaml
CHANGELOG.md
```

Current initial target:

```text
0.1.0
```

## 6. Clean build artifacts

```bash
rm -rf dist build *.egg-info
uv build
```

Inspect wheel contents if packaging changed:

```bash
python -m zipfile -l dist/*.whl | sort
```

Confirm `continuity/plugin.yaml` and `continuity/py.typed` are present.

## 7. Tag release

```bash
git tag v0.1.0
git push origin main --tags
```

Only push after deciding the GitHub remote and repository are correct.

## 8. GitHub release notes

Suggested sections:

```markdown
## Summary

Initial alpha release of Hermes Continuity Memory.

## Features

- SQLite/FTS continuity store
- budgeted prefetch
- inspection tools
- session marker extraction
- project capsules
- optional sqlite-hash vector backend
- built-in memory mirroring
- skill links

## Limitations

- no neural embeddings yet
- no repo/document ingestion yet
- no broad LLM summarization yet
- no multi-user ACLs
```
