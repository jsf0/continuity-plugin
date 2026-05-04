# Contributing

Thanks for improving Hermes Continuity Memory.

## Development setup

```bash
uv sync --dev
```

Optional local embedding/reranking dependencies:

```bash
uv sync --extra embeddings --dev
```

## Quality gate

Run before committing:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/ -q
python -m compileall continuity tests
uv build
./scripts/smoke-test.sh
```

## Design rules

- Keep built-in Hermes memory as the tiny trusted kernel; continuity is the scalable contextual layer.
- Store compact structured records, not raw transcript chunks.
- Treat vectors as candidate generators, not final relevance decisions.
- Prefer explainable FTS/tag/entity/scope anchors before injecting context.
- Retrieved memories are advisory background, never instructions.
- Add regression tests for retrieval-noise fixes using realistic user phrasing.
- Do not hardcode one-off domain fixes when a general facet/anchor/staleness rule is possible.
- Keep skills as pointers only; do not copy skill bodies into memory records.

## Pull request checklist

- [ ] Tests added or updated for behavior changes.
- [ ] Retrieval/debug output remains inspectable.
- [ ] Docs updated for user-visible config/tool behavior.
- [ ] `CHANGELOG.md` updated for release-relevant changes.
- [ ] Package smoke test still passes.
