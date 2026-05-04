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
python -m compileall continuity tests
uv build
./scripts/smoke-test.sh
```

## 3. Inspect package contents

```bash
python -m zipfile -l dist/*.whl | sort
```

Confirm these files are present:

```text
continuity/plugin.yaml
continuity/py.typed
continuity/__init__.py
continuity/retrieval.py
continuity/store.py
```

## 4. Run isolated install smoke

The repository smoke test creates a temporary `HERMES_HOME`, installs the plugin, initializes it, exercises add/search/prefetch/delete, verifies memory mirroring and skill links, and checks wheel metadata when `uv` is available:

```bash
./scripts/smoke-test.sh
```

Expected output ends with:

```text
smoke test ok
```

## 5. Review docs

Confirm these are current:

- `README.md`
- `CHANGELOG.md`
- `docs/INSTALL.md`
- `docs/CONFIGURATION.md`
- `docs/TROUBLESHOOTING.md`
- `docs/SPEC.md`
- `CONTRIBUTING.md`
- `SECURITY.md`

## 6. Bump version if needed

Update version in:

```text
pyproject.toml
continuity/plugin.yaml
CHANGELOG.md
```

Initial alpha target:

```text
0.1.0
```

## 7. Clean build artifacts

```bash
rm -rf dist build *.egg-info
uv build
```

Do not commit build artifacts.

## 8. Prepare GitHub repository

Before making the repo public, confirm:

- repository description is set;
- topics include `hermes-agent`, `memory`, `sqlite`, `rag`, and `llm-agent`;
- Issues are enabled;
- Actions are enabled;
- default branch is `main`;
- branch protection requires CI after the first green run;
- no local runtime DBs, caches, secrets, `.venv`, or `dist/` artifacts are tracked.

## 9. Tag release

Only push after deciding the GitHub remote and repository are correct.

```bash
git tag v0.1.0
git push origin main --tags
```

## 10. GitHub release notes

Suggested draft:

```markdown
## Summary

Initial alpha release of Hermes Continuity Memory: a local-first structured memory provider for Hermes Agent.

## Features

- SQLite/FTS continuity store
- budgeted prefetch
- inspection/debug tools
- session marker extraction
- project capsules
- optional vector retrieval and reranking
- association graph for implicit context rescue
- built-in memory mirroring
- skill links
- stale-memory lifecycle

## Limitations

- no repository/document ingestion yet
- no broad LLM summarization yet
- no multi-user ACLs
- retrieval quality is intentionally conservative and still tuning-sensitive
```
