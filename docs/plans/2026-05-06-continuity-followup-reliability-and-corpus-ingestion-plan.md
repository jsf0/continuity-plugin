# Continuity Follow-up Reliability and Corpus Ingestion Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task when we return to this work.

**Goal:** Capture the next continuity-memory improvement backlog so we can resume later without losing context.

**Architecture:** Continue improving the live/repo continuity plugin through small, verified maintenance and reliability milestones. Prioritize cleanup and measurement before further retrieval tuning, then return to corpus ingestion with a focus on high-quality LLM extraction, review/import flow, and eval-driven validation.

**Tech Stack:** Hermes Agent continuity memory provider, SQLite continuity DB, FTS/vector/reranker retrieval, association graph, quality gates, dream maintenance, corpus ingestion modules under `continuity/ingest/`, pytest, ruff, compileall.

---

## Context

This plan was created after confirming that write-path quality gates are live and working in the active Discord/Hermes session. A temporary sparse record was correctly enriched with `quality` metadata and surfaced by `continuity_quality_report`; after deletion the report returned clean.

The next reliability issues are mostly retrieval hygiene and lifecycle management, not basic write-path health. Keep corpus ingestion on the roadmap; the user explicitly said not to forget returning to it.

Current live observations from 2026-05-06:

- `continuity_status` showed provider initialized, 37 records, vectors and reranker enabled/healthy, association graph enabled.
- `continuity_quality_report` showed no persisted warning records after the temp smoke record was deleted.
- `continuity_prune_stale(dry_run=true)` found 5 stale/superseded candidates.
- Debug retrieval for continuity improvement queries still showed association graph/meta-query over-recall.
- Debug retrieval for the new corpus-ingestion reminder worked cleanly for exact phrasing, but broader corpus-ingestion roadmap phrasing still pulled general continuity retrieval/eval neighbors through graph expansion.

## Non-goals

- Do not hard-delete stale records by default.
- Do not tune graph/retrieval from vibes; add or run evals first.
- Do not restart the active Hermes gateway mid-session unless explicitly approved.
- Do not make corpus-ingestion LLM extraction automatically route to a provider; keep it explicitly configured to avoid accidental data exfiltration.

---

## Task 1: Archive the current stale dry-run candidates after review

**Objective:** Remove known superseded records from normal retrieval without deleting audit history.

**Files:**
- Likely no code changes.
- Live DB: inspect via continuity tools, not direct mutation unless tools are insufficient.
- Optional docs update: `docs/plans/2026-05-06-continuity-followup-reliability-and-corpus-ingestion-plan.md`

**Step 1: Re-run stale dry run**

Run via Hermes tool:

```text
continuity_prune_stale(dry_run=true, limit=20)
```

Expected: stale candidates similar to:

```text
mirror_memory_1ac6b0e58e4202dc -> superseded by mirror_memory_5f05c28480c573dd
r_f34ef3d1151f4c77923e0827cd5156b8 -> superseded by r_20260504_continuity_facet_compat_impl
capsule_98730bb57ba592c2 -> superseded by capsule_36576c9fe24a9de8
r_20260504_realworld_continuity_eval -> superseded by r_20260504_continuity_facet_compat_impl
mirror_memory_998f6167d73b35de -> superseded by mirror_memory_5f05c28480c573dd
```

**Step 2: Spot-check candidates**

For each candidate, run:

```text
continuity_get(id="<candidate_id>")
continuity_get(id="<superseded_by_id>")
```

Verify:

- the newer record genuinely supersedes the older one;
- no unique high-value fact would disappear from normal retrieval;
- the old record can safely be archived rather than deleted.

**Step 3: Archive conservatively**

Run either the batch prune if all candidates look correct:

```text
continuity_prune_stale(dry_run=false, mode="archive", limit=20)
```

Or archive one-by-one:

```text
continuity_archive(id="<candidate_id>", reason="superseded by <newer_id>", superseded_by="<newer_id>")
```

**Step 4: Verify stale exclusion**

Run:

```text
continuity_search(query="continuity corpus ingestion roadmap", limit=5)
continuity_debug_retrieval(query="corpus ingestion roadmap continuity memory", scope_project="hermes-continuity-memory", limit=5)
continuity_search(query="<archived old title>", include_stale=true, limit=5)
```

Expected:

- archived records do not appear in normal retrieval;
- archived records remain inspectable with `include_stale=true`;
- relevant current records still retrieve.

**Step 5: Record outcome**

If this changes repo docs or a plan status, commit:

```bash
git -C /root/hermes-continuity-memory status --short
git -C /root/hermes-continuity-memory add docs/plans/2026-05-06-continuity-followup-reliability-and-corpus-ingestion-plan.md
git -C /root/hermes-continuity-memory commit -m "docs: update continuity stale cleanup plan"
```

---

## Task 2: Run and backfill a retrospective quality audit for existing records

**Objective:** Identify older pre-quality-gate records that are sparse, generic, over-broad, or missing useful metadata even if `continuity_quality_report` is currently clean.

**Files:**
- Inspect: `continuity/record_quality.py`
- Inspect: `scripts/report-record-quality.py`
- Potentially modify: `scripts/report-record-quality.py`
- Potentially modify: `continuity/tools.py` or provider tool definitions if a backfill tool is added
- Tests: add or update `tests/test_write_path_quality_regressions.py` or a new `tests/test_record_quality_backfill.py`

**Step 1: Run current retrospective report script against a non-mutating path**

Run:

```bash
cd /root/hermes-continuity-memory
PYTHONPATH=. python scripts/report-record-quality.py --help
```

Then run the appropriate dry-run/report command from the help output against the live DB or a copied DB.

Expected: report recomputes quality for existing records rather than relying only on persisted `quality_json`.

**Step 2: If no safe backfill exists, add a dry-run backfill mode**

Write tests first. Desired behavior:

- recomputes quality for all active records;
- reports records where recomputed warnings differ from persisted quality;
- supports dry-run by default;
- does not put warnings into `details`, tags, entities, FTS, or embedding text.

**Step 3: Add/verify backfill implementation**

Implementation constraints:

- reuse `record_quality.py` and existing enrichment functions;
- preserve record IDs, source refs, status, trust level, and timestamps except `updated_at` only when intentionally writing quality metadata;
- avoid creating new association graph edges solely due to quality backfill;
- avoid vector updates unless `embedding_text` changes, which it should not for quality-only metadata.

**Step 4: Run tests**

Run:

```bash
cd /root/hermes-continuity-memory
uv run pytest tests/test_write_path_quality_regressions.py -q
uv run pytest tests/ -q
uv run ruff format --check .
uv run ruff check .
python -m compileall continuity tests
```

Expected: all pass.

**Step 5: Apply only after reviewing dry-run output**

If dry-run flags records, classify them:

- archive obvious junk/superseded records;
- backfill quality metadata for records that should stay active;
- repair important but sparse records manually where needed.

---

## Task 3: Enable or schedule report-only dream maintenance

**Objective:** Make memory maintenance visible and repeatable without mutating records automatically.

**Files:**
- Inspect: `continuity/dream.py` or equivalent dream implementation files
- Inspect: provider config handling in `continuity/__init__.py`
- Inspect docs: `docs/CONFIGURATION.md`, `docs/TROUBLESHOOTING.md`
- Potential docs update: `docs/CONFIGURATION.md`

**Step 1: Inspect current dream status**

Run:

```text
continuity_status()
continuity_dream(mode="report", limit=20)
```

Expected currently:

```text
dream_enabled: false
dream_mode: report
dream_last_run_at: null
```

Manual report should not archive or delete records.

**Step 2: Verify report content**

The report should include at least:

- record counts before/after;
- stale candidates;
- quality warning counts;
- vector/index parity;
- association edge inventory or summary;
- notes on whether any mutations occurred.

**Step 3: Decide scheduling mechanism later**

Options:

- plugin `run_on_turn` / scheduled check if configured;
- Hermes cron job that calls a self-contained dream/report prompt;
- systemd timer or external scheduler.

Start with report-only. Do not enable archive modes until report output has been reviewed over multiple runs.

**Step 4: Document exact config**

If docs need updates, add a report-only example:

```yaml
memory:
  provider: continuity
  continuity:
    dream:
      enabled: true
      schedule: "03:30"
      timezone: "UTC"
      mode: "report"
      run_on_turn: true
      run_on_initialize: true
```

**Step 5: Verify no mutation**

Run before/after:

```text
continuity_status()
continuity_dream(mode="report", limit=20)
continuity_status()
```

Expected: no record count drop, no archived/deleted IDs, only `dream:last_report` or equivalent state changes.

---

## Task 4: Prune/rebuild association graph after cleanup

**Objective:** Reduce graph over-recall after stale/archive cleanup and quality backfill.

**Files:**
- Inspect: `continuity/association.py`
- Inspect: `continuity/store.py`
- Inspect: `continuity/retrieval.py`
- Tests: association/retrieval regression tests, likely `tests/test_association*.py` and retrieval quality tests

**Step 1: Capture current graph inventory**

Run:

```text
continuity_association_edges(limit=50)
continuity_debug_retrieval(query="corpus ingestion roadmap continuity memory", scope_project="hermes-continuity-memory", limit=5)
continuity_debug_retrieval(query="don't forget that we want to come back to the corpus ingestion too", scope_project="hermes-continuity-memory", limit=5)
```

Save/compare:

- included neighbors;
- cut neighbors;
- activation seeds;
- unrelated selected records.

**Step 2: Rebuild graph in a safe environment first**

Use a copied DB or test fixture first. Do not mutate the live DB until the rebuild path is verified.

Expected behavior after cleanup:

- exact corpus-ingestion reminder still retrieves the direct reminder record only;
- corpus-ingestion roadmap query retrieves corpus-ingestion design and reminder records;
- continuity retrieval/eval records are less likely to crowd top-k unless the query is explicitly about retrieval tuning.

**Step 3: Add regression tests before tuning**

Add tests for:

```text
Query: don't forget that we want to come back to the corpus ingestion too
Expected: selects reminder record directly; no graph neighbors required.

Query: corpus ingestion roadmap continuity memory
Expected: selects corpus ingestion design/reminder records; does not select boat/towing regression.

Query: what did we fix in continuity retrieval?
Expected: selects retrieval/facet/noise records.
```

**Step 4: Tune graph gates only if tests prove noise**

Potential tuning areas:

- stricter facet compatibility for meta/roadmap queries;
- lower graph fanout for memory-system queries;
- suppress `active_project_state` graph neighbors when query has stronger direct corpus-ingestion records;
- avoid activation from stale/archived/low-quality records;
- rebuild persisted edges after changing association scoring.

**Step 5: Verify live behavior after code/test success**

Run full gates before touching live plugin:

```bash
cd /root/hermes-continuity-memory
uv run pytest tests/ -q
uv run ruff format --check .
uv run ruff check .
python -m compileall continuity tests
```

If live plugin sync is needed, compare/copy package files carefully and defer gateway restart unless approved.

---

## Task 5: Add or expand retrieval regression evals

**Objective:** Make future retrieval/graph/reranker tuning measurable instead of subjective.

**Files:**
- Inspect existing retrieval eval tests under `tests/`
- Potentially create: `tests/test_retrieval_regressions_live_cases.py`
- Potentially update demo/eval scripts under `scripts/`
- Potential docs update: `docs/TROUBLESHOOTING.md` or `docs/RELEASE.md`

**Step 1: Inventory current retrieval tests**

Run:

```bash
cd /root/hermes-continuity-memory
python - <<'PY'
from pathlib import Path
for p in Path('tests').glob('**/*.py'):
    txt = p.read_text(errors='ignore')
    if 'debug_retrieval' in txt or 'association' in txt or 'retrieval' in p.name:
        print(p)
PY
```

**Step 2: Define eval cases**

Add cases for:

- low-information followups: `how about now?`, `is it better?`, `ok so is it fixed?`
- memory-meta queries: `what did we fix in continuity retrieval?`
- user-preference queries: `how do I prefer you handle big code changes?`
- ambiguous Framework hardware/software queries;
- stale-record exclusion;
- graph rescue where useful, e.g. implicit boat/towing context;
- negative queries where no memory should be injected;
- corpus-ingestion roadmap queries.

**Step 3: Include positive and negative assertions**

Each eval should assert both:

- expected records/titles/kinds are selected in top-k;
- forbidden records/titles/kinds are not selected.

For example:

```python
def test_corpus_ingestion_roadmap_does_not_select_boat_regression(...):
    result = retriever.debug_retrieval("corpus ingestion roadmap continuity memory")
    titles = [r.title for r in result.selected]
    assert any("corpus ingestion" in title.lower() for title in titles)
    assert "Continuity retrieval boat/towing regression result" not in titles
```

**Step 4: Run targeted and full tests**

Run:

```bash
cd /root/hermes-continuity-memory
uv run pytest tests/test_retrieval_regressions_live_cases.py -q
uv run pytest tests/ -q
uv run ruff format --check .
uv run ruff check .
python -m compileall continuity tests
```

Expected: all pass before tuning claims.

**Step 5: Use evals before changing thresholds**

Only tune graph/reranker thresholds after a test fails or a live debug case demonstrates a specific regression.

---

## Task 6: Return to corpus ingestion work

**Objective:** Resume corpus ingestion with emphasis on high-quality LLM extraction, review/import safety, and retrieval evals for imported corpora.

**Files:**
- Read first: `docs/plans/2026-05-05-corpus-ingestion-spec.md`
- Read first: `docs/plans/2026-05-05-corpus-ingestion-implementation-steps.md`
- Inspect: `continuity/ingest/`
- Inspect tests: `tests/ingest/`
- Potential docs update: corpus ingestion docs and README sections

**Step 1: Re-read existing corpus ingestion plans**

Run:

```bash
cd /root/hermes-continuity-memory
git status --short
git log --oneline -n 12 -- continuity/ingest tests/ingest docs/plans/2026-05-05-corpus-ingestion-*.md
```

Use `read_file` for:

```text
docs/plans/2026-05-05-corpus-ingestion-spec.md
docs/plans/2026-05-05-corpus-ingestion-implementation-steps.md
```

**Step 2: Inventory implemented ingestion modules**

Inspect:

```text
continuity/ingest/models.py
continuity/ingest/connectors.py
continuity/ingest/parsers.py
continuity/ingest/segmenters.py
continuity/ingest/pipeline.py
continuity/ingest/validation.py
continuity/ingest/extractors.py
continuity/ingest/dedupe.py
continuity/ingest/review.py
continuity/ingest/importer.py
continuity/ingest/llm_extractors.py
```

Confirm which milestones are complete and which are partial.

**Step 3: Prioritize LLM extraction quality over deterministic extractor breadth**

The user preference is to focus production effort on excellent LLM-based extraction. Deterministic extractors are useful as validation/fallback scaffolding, not the main production quality path.

Key requirements:

- LLM extraction must be explicitly user-configured;
- no accidental provider routing or data exfiltration;
- per-segment progress/resume cache;
- robust JSON repair/retry handling;
- source refs on every candidate;
- safety gates for prompt-injection-like and example-derived candidates.

**Step 4: Validate via temp DB before live import**

Run ingestion into a temporary SQLite continuity DB first. Evaluate:

- expected-record recall;
- top-1/top-3 precision;
- forbidden title checks;
- negative/noise queries;
- selected-title inspection, not just pass/fail.

**Step 5: Add corpus-ingestion retrieval eval generation/runner if incomplete**

Expected eval features:

- positive expected titles/tags/entities;
- negative/forbidden records;
- top-k precision thresholds;
- report output that identifies noisy imported records;
- dry-run by default.

**Step 6: Run ingestion gates**

Run at minimum:

```bash
cd /root/hermes-continuity-memory
uv run ruff check --fix continuity/ingest tests/ingest
uv run ruff format continuity/ingest tests/ingest
uv run pytest tests/ingest -q
uv run pytest tests/ -q
python -m compileall continuity tests
```

**Step 7: Keep repo clean and commit each milestone**

Before and after each corpus ingestion milestone:

```bash
git status --short
```

After verified work:

```bash
git add continuity/ingest tests/ingest docs
git commit -m "feat: improve corpus ingestion <specific milestone>"
```

---

## Resumption checklist

When returning to this plan:

1. Load `hermes-continuity-memory`, `writing-plans`, and likely `test-driven-development` skills.
2. Run `continuity_status`, `continuity_quality_report`, and `continuity_prune_stale(dry_run=true)`.
3. Check `/root/hermes-continuity-memory` git status and recent commits.
4. Decide whether the session goal is live behavior, repo implementation, or both.
5. If live behavior matters, verify live plugin path `~/.hermes/plugins/continuity/` vs repo package parity before editing.
6. Defer Hermes gateway restart until final checkpoint unless explicitly approved.
