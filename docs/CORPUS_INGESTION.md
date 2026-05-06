# Corpus ingestion

Corpus ingestion is an offline, review-first pipeline for distilling source documents into compact, source-linked continuity records. It is intentionally not raw chunk RAG: the output is candidate memory records that can be reviewed, imported, refreshed, and evaluated through the normal continuity store.

## Safe default flow

Run ingestion into an output directory first:

```bash
uv run continuity-ingest run /path/to/corpus \
  --include '**/*.md' \
  --recipe docs \
  --policy require-review \
  --project my-project \
  --output /tmp/continuity-ingest-my-project
```

This does **not** mutate your live memory DB. It writes review artifacts:

```text
manifest.json
inventory.jsonl
segments.jsonl
candidate-records.jsonl
merged-records.jsonl
approved-records.jsonl
pending-records.jsonl
rejected-candidates.jsonl
review-decisions.jsonl
retrieval-evals.jsonl
ingestion-stats.json
review.md
import-report.md
```

Use `review.md`, `pending-records.jsonl`, and `rejected-candidates.jsonl` to inspect quality before importing anything.

## Scale/debug statistics

Every `run` writes `ingestion-stats.json`. This is the first place to look when stress testing large corpora.

Important fields:

- `summary.source_count` — discovered parseable sources.
- `summary.segment_count` — generated source segments.
- `summary.candidate_count` — pre-dedupe normalized candidates.
- `summary.merged_candidate_count` — post-dedupe candidates.
- `summary.approved_count` / `summary.pending_count` — review split.
- `sources.by_type` — source type inventory, e.g. Markdown vs text.
- `segments.total_chars`, `avg_chars`, `max_chars` — segmentation size profile.
- `segments.by_source_type` — segment distribution by originating source type.
- `candidates.by_kind` — memory type distribution.
- `candidates.avg_confidence` / `avg_importance` — review-signal sanity checks.
- `rejections.by_reason` — quality/safety/dedupe failure modes.

Example quick inspection:

```bash
python - <<'PY'
import json
from pathlib import Path
stats = json.loads(Path('/tmp/continuity-ingest-my-project/ingestion-stats.json').read_text())
print(json.dumps(stats['summary'], indent=2, sort_keys=True))
print(json.dumps(stats['candidates']['by_kind'], indent=2, sort_keys=True))
print(json.dumps(stats['rejections']['by_reason'], indent=2, sort_keys=True))
PY
```

If candidate volume explodes, inspect `candidates.by_kind`, `rejections.by_reason`, and `segments.avg_chars` before importing. Excessive `procedure_candidate` or generic `artifact_summary` counts usually mean the recipe/extractor is too broad for the corpus.

## Validate in a temporary DB

After review, validate approved records and generated evals in a temporary DB:

```bash
uv run continuity-ingest validate-import \
  /tmp/continuity-ingest-my-project/approved-records.jsonl \
  --evals /tmp/continuity-ingest-my-project/retrieval-evals.jsonl \
  --report /tmp/continuity-ingest-my-project/temp-eval-report.jsonl
```

`validate-import` imports into a temporary SQLite DB and exits nonzero if import or eval fails. It does not touch your live continuity DB.

## Import only after review

Import approved records only when the review and temporary validation look good:

```bash
uv run continuity-ingest import \
  /tmp/continuity-ingest-my-project/approved-records.jsonl \
  --db-path ~/.hermes/continuity/continuity.db \
  --apply
```

Without `--apply`, import is a dry run.

## LLM extraction is explicit opt-in

The default extractor is deterministic and local. LLM extraction only runs when explicitly requested:

```bash
uv run continuity-ingest run /path/to/corpus \
  --extractor llm \
  --llm-command 'uv run continuity-ingest-llama-cpp --endpoint http://127.0.0.1:8080/v1/chat/completions' \
  --policy require-review \
  --output /tmp/continuity-ingest-llm
```

Use local or intentionally tunneled endpoints for private corpora. Source text and LLM output are treated as untrusted data and still pass through normalization, safety gates, quality gates, dedupe, and review.

## Refresh changed corpora

Compare a later scan with a previous inventory:

```bash
uv run continuity-ingest refresh /path/to/corpus \
  --previous-inventory /tmp/continuity-ingest-my-project/inventory.jsonl \
  --include '**/*.md' \
  --output /tmp/continuity-refresh-my-project
```

With `--db-path` and `--apply`, refresh can soft-archive lower-trust corpus-derived records whose source files changed or disappeared. It does not hard-delete records.

## Stress-test example

To test ingestion behavior at larger scale, generate or point at a synthetic corpus and run the normal review-first pipeline. Inspect `ingestion-stats.json` instead of importing immediately.

A healthy run should show:

- source and segment counts that match expectations;
- candidate kinds appropriate for the recipe;
- dedupe reducing obvious duplicates;
- unsafe or low-information candidates rejected or held pending;
- generated eval count matching approved records for auto-review policies.

Run the ingestion regression suite after changing ingestion behavior:

```bash
uv run pytest tests/ingest -q
uv run pytest tests/ -q
```
