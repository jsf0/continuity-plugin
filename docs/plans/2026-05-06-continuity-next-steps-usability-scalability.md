# Continuity plugin next steps: usability and scalability

Date: 2026-05-06

## Current assessment

The continuity plugin is usable and substantially healthier than the earlier noisy-retrieval state. The main wins are:

- hybrid retrieval is active with vectors, FTS, metadata anchors, facets, reranking, and bounded association-graph rescue;
- write-path quality metadata is injected separately from retrieval text via `quality_json`;
- low-information follow-ups now prefer no context over wrong context;
- memory-system/status records are gated away from ordinary non-meta queries;
- facet compatibility prevents polysemous terms such as `Framework` from crossing hardware/software domains;
- pruning/archiving is soft, dry-run/report-first, and restoreable;
- corpus ingestion is an offline producer of compact, source-linked continuity records rather than raw chunk dumping;
- corpus imports can now be validated in a temporary DB before touching live memory.

## Recommended next steps

1. **Calibrate reranker/direct relevance for personal-context queries.**
   - Boat/towing retrieval now returns the intended Raptor and trailerable-boat context, but it still leans on association-graph rescue because reranker scores are low.
   - Add or extend eval cases for personal preference, vehicle/towing, boating, and work-style queries.
   - Tune direct scoring so strong tag/entity matches can survive without relying entirely on graph rescue.

2. **Run a larger retrieval regression suite with negative/noise cases.**
   - Include positive anchored queries, low-information follow-ups, memory-meta queries, software/hardware ambiguity, and project-status ambiguity.
   - Measure precision, not just recall: expected top-k, forbidden titles/tags, and no-context expectations.
   - Keep regression fixtures generic enough that fixes are not hardcoded to one domain.

3. **Backfill or recompute quality metadata on older live records.**
   - `continuity_quality_report` only sees persisted quality metadata.
   - Use the quality backfill audit tooling to identify older records that predate `quality_json` or have sparse metadata.
   - Backfill conservatively and keep diagnostics out of `summary`, `details`, tags, entities, FTS, and embedding text.

4. **Review and archive stale mirror candidates.**
   - Current report/dream runs identify older built-in memory mirrors that appear superseded.
   - Review candidates first, then use soft archive mode; do not hard-delete by default.
   - Explicit user preferences and high-importance facts should remain protected from age-only pruning.

5. **Turn dream/report maintenance into a scheduled or operator-visible workflow.**
   - Keep default behavior non-destructive.
   - Prefer report mode first, then archive-safe once reports look sane.
   - If unattended wall-clock execution is desired, pair plugin dream checks with external cron/systemd scheduling; the plugin alone only checks due-ness during provider initialization/turn sync.

6. **Continue ingestion recipe and eval work using temp-DB validation by default.**
   - Treat corpus ingestion as review-first until a corpus/recipe is proven.
   - Keep LLM extraction explicitly user-configured to avoid accidental data exfiltration.
   - Maintain source refs, hashes, trust levels, and refresh/staleness artifacts.
   - Avoid immediate noisy graph edge creation for bulk imports unless a deliberate association rebuild/eval step follows.

7. **Keep live plugin and dev repo parity explicit.**
   - The development repo is `/root/hermes-continuity-memory`.
   - The live plugin path is `/root/.hermes/plugins/continuity`.
   - Before claiming a runtime fix is live, compare/sync the paths, compile the live plugin, and restart/verify the gateway.

## Current verification commands

```bash
cd /root/hermes-continuity-memory
uv run ruff check .
uv run pytest tests/ -q
python -m compileall continuity tests

python -m compileall /root/.hermes/plugins/continuity
PYTHONPATH=/root/.hermes/plugins python - <<'PY'
import continuity
print(continuity.__file__)
PY
```

## Release-readiness reminders

Before public release or strong claims:

- run full tests and smoke tests;
- inspect retrieval regressions and demo results;
- run secret scans;
- inspect built artifacts/wheels;
- confirm live-vs-repo parity;
- document dream/pruning behavior and non-destructive defaults;
- include small-model before/after evidence if claiming continuity helps smaller models.
