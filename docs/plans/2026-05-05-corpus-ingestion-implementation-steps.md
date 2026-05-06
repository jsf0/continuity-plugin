# Corpus Ingestion Implementation Steps

> **For Hermes:** Use this as the implementation roadmap for `/root/hermes-continuity-memory/docs/plans/2026-05-05-corpus-ingestion-spec.md`. Before coding, load `hermes-continuity-memory`, `writing-plans`, and `test-driven-development`. Implement one milestone at a time with tests. Do not rewrite runtime retrieval.

**Goal:** Add a flexible, offline corpus ingestion pipeline that produces scoped, source-linked continuity records from arbitrary corpora while preserving existing continuity retrieval behavior.

**Architecture:** Build a new ingestion subsystem that normalizes input sources into `SourceDocument -> ParsedDocument -> SourceSegment -> CandidateRecord`, then reviews/imports approved records into the existing continuity store. Keep runtime retrieval unchanged except for minimal support needed to preserve source refs/trust metadata.

**Tech Stack:** Python 3.11+, existing `continuity` package, SQLite-backed continuity store, JSONL artifacts, `uv`, `pytest`, `ruff`. Keep MVP dependencies at zero unless explicitly justified.

---

## Milestone 0: Verify baseline and decide package layout

**Objective:** Establish current repo health and choose the minimal package organization.

**Steps:**

1. Run baseline checks:
   ```bash
   cd /root/hermes-continuity-memory
   uv run ruff format --check .
   uv run ruff check .
   uv run pytest tests/ -q
   python -m compileall continuity tests
   ```
2. Inspect `continuity/models.py`, `continuity/store.py`, `continuity/tools.py`, and `continuity/security.py` before designing imports.
3. Use this package layout for MVP:
   ```text
   continuity/ingest/
     __init__.py
     models.py
     jsonl.py
     pipeline.py
     registry.py
     validation.py
     reports.py
     connectors.py
     parsers.py
     segmenters.py
     extractors.py
     dedupe.py
     review.py
     importer.py
     cli.py
   ```
4. Add tests under:
   ```text
   tests/ingest/
   ```
5. Add fixtures under:
   ```text
   tests/fixtures/ingestion/simple_docs/
   ```

**Acceptance:** Baseline test state is known, and ingestion has a clear module/test location.

---

## Milestone 1: Core ingestion models and JSONL helpers

**Objective:** Create stable internal models before implementing any parser/extractor logic.

**Create:**

- `continuity/ingest/__init__.py`
- `continuity/ingest/models.py`
- `continuity/ingest/jsonl.py`
- `tests/ingest/test_models.py`
- `tests/ingest/test_jsonl.py`

**Implement models:**

- `SourceDocument`
- `ParsedBlock`
- `ParsedDocument`
- `SourceLocation`
- `SourceSegment`
- `SourceRef`
- `CandidateRecord`
- `IngestionRunManifest`
- `Rejection`
- `ReviewDecision`

Use stdlib dataclasses for zero new dependencies. Include `to_dict()` / `from_dict()` helpers, basic validation methods, and stable ID/hash helper functions.

**Steps:**

1. Write tests for creating valid `SourceDocument`, `SourceSegment`, and `CandidateRecord`.
2. Write tests that missing source refs fail validation for corpus candidates.
3. Write tests for JSONL round-trip.
4. Implement dataclasses and validation.
5. Implement `read_jsonl(path)` and `write_jsonl(path, rows)`.
6. Run:
   ```bash
   uv run pytest tests/ingest/test_models.py tests/ingest/test_jsonl.py -q
   ```

**Acceptance:** Ingestion objects serialize/deserialize cleanly and enforce source-ref presence.

---

## Milestone 2: Local-files connector and inventory output

**Objective:** Discover local corpus files and write `inventory.jsonl`.

**Create/modify:**

- `continuity/ingest/connectors.py`
- `tests/ingest/test_connectors.py`
- fixture files under `tests/fixtures/ingestion/simple_docs/`

**Fixture corpus:**

```text
tests/fixtures/ingestion/simple_docs/
  README.md
  docs/architecture.md
  docs/release.md
  docs/noisy.md
  docs/bad_prompt_injection.md
  docs/fake_secret.md
```

**Steps:**

1. Write tests for include/exclude glob behavior.
2. Write tests that file source IDs are stable.
3. Write tests that SHA-256 and mtime metadata are populated.
4. Implement `LocalFilesConnector.discover(root, include, exclude, project, repo)`.
5. Ensure binary/unreadable files are skipped with warnings rather than crashing.
6. Run:
   ```bash
   uv run pytest tests/ingest/test_connectors.py -q
   ```

**Acceptance:** A local directory becomes deterministic `SourceDocument` rows.

---

## Milestone 3: Markdown/plaintext parsing and segmentation

**Objective:** Convert discovered docs into source-located segments.

**Create/modify:**

- `continuity/ingest/parsers.py`
- `continuity/ingest/segmenters.py`
- `tests/ingest/test_parsers.py`
- `tests/ingest/test_segmenters.py`

**Steps:**

1. Write parser tests for Markdown headings, paragraphs, code blocks, and line locations.
2. Write parser tests for plaintext fallback.
3. Write segmenter tests for heading-section segmentation.
4. Write segmenter tests for fixed-window fallback when no headings exist.
5. Implement `MarkdownParser` using simple line-based parsing for MVP.
6. Implement `TextParser`.
7. Implement `HeadingSectionSegmenter`.
8. Implement `FixedWindowSegmenter`.
9. Run:
   ```bash
   uv run pytest tests/ingest/test_parsers.py tests/ingest/test_segmenters.py -q
   ```

**Acceptance:** Markdown/text files become useful `SourceSegment` rows with line source refs.

---

## Milestone 4: Pipeline orchestration and run directory artifacts

**Objective:** Wire inventory -> parse -> segment into a repeatable dry-run pipeline.

**Create/modify:**

- `continuity/ingest/pipeline.py`
- `continuity/ingest/reports.py`
- `tests/ingest/test_pipeline.py`

**Steps:**

1. Write integration test that runs pipeline on `simple_docs` fixture.
2. Assert output directory contains:
   ```text
   manifest.json
   inventory.jsonl
   segments.jsonl
   import-report.md
   ```
3. Implement `IngestionPipeline.run_inventory_and_segment(...)`.
4. Implement deterministic run ID override for tests.
5. Implement Markdown report summary.
6. Run:
   ```bash
   uv run pytest tests/ingest/test_pipeline.py -q
   ```

**Acceptance:** A user can perform a no-LLM dry run and inspect inventory/segments.

---

## Milestone 5: Validation, safety gates, and normalization

**Objective:** Add conservative quality/safety checks before extraction/import.

**Create/modify:**

- `continuity/ingest/validation.py`
- `tests/ingest/test_validation.py`

**Steps:**

1. Reuse or wrap existing `continuity/security.py` if suitable; do not duplicate complex security logic unnecessarily.
2. Write tests rejecting prompt-injection-like candidate text.
3. Write tests rejecting/redacting fake secret-like candidate text.
4. Write tests enforcing summary/detail length caps.
5. Write tests setting default `trust_level="corpus_distilled"`.
6. Write tests normalizing tags/entities/title.
7. Implement `CandidateNormalizer` and `SafetyGate`.
8. Run:
   ```bash
   uv run pytest tests/ingest/test_validation.py -q
   ```

**Acceptance:** Unsafe/weak candidate records are blocked or flagged before import.

---

## Milestone 6: Rule-based MVP extractors

**Objective:** Generate useful candidates without requiring an LLM yet.

**Why before LLM:** It makes tests deterministic and proves the candidate/review/import flow.

**Create/modify:**

- `continuity/ingest/extractors.py`
- `tests/ingest/test_extractors.py`

**Implement MVP extractors:**

1. `ProjectCapsuleExtractor`
   - Creates one `artifact_summary` per corpus/project from README-like segments.
2. `ProcedureCandidateExtractor`
   - Detects sections with release/test/deploy/checklist/procedure language.
3. `CodeOrConfigFactExtractor`
   - Detects obvious test/build commands from docs/config text.
4. `EvalCaseGenerator`
   - Generates simple positive evals from accepted candidate titles/tags.

**Steps:**

1. Write tests using fixture `docs/release.md` to produce a procedure candidate.
2. Write tests using fixture `README.md` to produce a project capsule.
3. Write tests that noisy docs produce zero candidates.
4. Implement deterministic extractors.
5. Pass all candidates through normalizer/safety gate.
6. Run:
   ```bash
   uv run pytest tests/ingest/test_extractors.py -q
   ```

**Acceptance:** The pipeline can generate useful candidate records deterministically.

---

## Milestone 7: Dedupe and review artifacts

**Objective:** Prevent memory spam and create human-reviewable outputs.

**Create/modify:**

- `continuity/ingest/dedupe.py`
- `continuity/ingest/review.py`
- `tests/ingest/test_dedupe.py`
- `tests/ingest/test_review.py`

**Steps:**

1. Write tests for duplicate normalized title + kind + scope.
2. Write tests for source-ref duplicate merging.
3. Write tests for review policy decisions:
   - safe high-confidence local docs -> approved in `safe-auto`
   - personal/user preference -> pending review
   - low confidence -> pending or rejected
4. Implement `BasicDeduper`.
5. Implement review policies: `propose`, `require-review`, `conservative`, `safe-auto`.
6. Generate:
   ```text
   candidate-records.jsonl
   merged-records.jsonl
   approved-records.jsonl
   pending-records.jsonl
   rejected-candidates.jsonl
   review.md
   ```
7. Run:
   ```bash
   uv run pytest tests/ingest/test_dedupe.py tests/ingest/test_review.py -q
   ```

**Acceptance:** Candidate records are deduped and split into approved/pending/rejected outputs.

---

## Milestone 8: Continuity importer with idempotency

**Objective:** Import approved records into the existing continuity store without duplicates.

**Create/modify:**

- `continuity/ingest/importer.py`
- `tests/ingest/test_importer.py`

**Steps:**

1. Inspect `continuity/store.py` APIs and current `ContextRecord` model.
2. Write test importing one approved `CandidateRecord` into a temp DB/store.
3. Assert `continuity_search` or store search finds it.
4. Write test re-importing same record does not create duplicate.
5. Decide source refs MVP storage:
   - preferred: first-class metadata/source refs if existing model supports it;
   - fallback: serialize source refs as structured JSON in `details` with a clear marker.
6. Implement deterministic imported record ID based on corpus/source/kind/title hash.
7. Implement `ContinuityImporter.import_records(..., dry_run=False)`.
8. Run:
   ```bash
   uv run pytest tests/ingest/test_importer.py -q
   ```

**Acceptance:** Approved candidate records become searchable continuity records; import is idempotent.

---

## Milestone 9: CLI for staged and recipe-driven MVP

**Objective:** Provide a usable command-line interface.

**Create/modify:**

- `continuity/ingest/cli.py`
- `pyproject.toml`
- `tests/ingest/test_cli.py`

**Add script entry point:**

```toml
[project.scripts]
continuity-ingest = "continuity.ingest.cli:main"
```

**Commands for MVP:**

```bash
continuity-ingest run PATH --recipe docs --dry-run --output .ingestion/run-...
continuity-ingest inventory PATH --output inventory.jsonl
continuity-ingest segment inventory.jsonl --output segments.jsonl
continuity-ingest review candidate-records.jsonl --output-dir review/
continuity-ingest import approved-records.jsonl --dry-run
continuity-ingest import approved-records.jsonl --apply
```

**Steps:**

1. Write CLI tests using `pytest` and temp dirs.
2. Implement argparse-based CLI; avoid adding Typer/Click for MVP unless desired later.
3. Ensure `--dry-run` is default for `run` and `import` unless `--apply` is present.
4. Run:
   ```bash
   uv run pytest tests/ingest/test_cli.py -q
   ```

**Acceptance:** Users can run the pipeline end-to-end from CLI.

---

## Milestone 10: Retrieval eval generation and runner

**Objective:** Measure whether imported records are retrievable without noise.

**Create/modify:**

- `continuity/ingest/eval.py`
- `tests/ingest/test_eval.py`

**Steps:**

1. Define eval case JSONL schema.
2. Generate simple eval cases from accepted candidates:
   - query based on title/summary
   - expected title/tags
   - forbidden tags optional
3. Write eval runner against temp continuity store.
4. Test positive record retrieval.
5. Test ambiguous/unrelated query retrieves no imported corpus records.
6. Add CLI command:
   ```bash
   continuity-ingest eval retrieval-evals.jsonl --home "$TMP_HERMES_HOME"
   ```
7. Run:
   ```bash
   uv run pytest tests/ingest/test_eval.py -q
   ```

**Acceptance:** Ingestion can prove useful recall and catch obvious noisy recall.

---

## Milestone 11: LLM-backed extractor behind an interface

**Objective:** Add flexible LLM extraction without making tests flaky or requiring credentials.

**Create/modify:**

- `continuity/ingest/llm.py`
- extend `continuity/ingest/extractors.py`
- `tests/ingest/test_llm_extractor.py`

**Steps:**

1. Define an `LLMClient` protocol with a single `complete(prompt) -> str` method.
2. Implement `LLMDurableMemoryExtractor` using injectable client.
3. Unit test with fake client returning fixed JSONL.
4. Test invalid JSONL response handling.
5. Test source refs are added/enforced even if model omits them.
6. Keep no network/API dependency in tests.
7. Add CLI option for LLM extraction later, e.g. `--extractor llm-durable-memory`.

**Acceptance:** LLM extraction is available but optional, testable, and isolated.

---

## Milestone 12: Refresh manifest and stale-source reporting

**Objective:** Track source hashes and prepare for safe refresh/staleness behavior.

**Create/modify:**

- `continuity/ingest/refresh.py`
- `tests/ingest/test_refresh.py`

**Steps:**

1. Store source -> records mapping in run manifest or separate `source-manifest.json`.
2. Write tests for unchanged source -> skip.
3. Write tests for changed source -> report `needs_reingestion`.
4. Write tests for deleted source -> report `archive_candidates`.
5. Implement report-only refresh first.
6. Add CLI command:
   ```bash
   continuity-ingest refresh PATH --previous-manifest source-manifest.json --report-only
   ```

**Acceptance:** Refresh can identify unchanged/changed/deleted sources without mutating DB by default.

---

## Milestone 13: Docs and smoke test

**Objective:** Make the feature pick-up-able by users and future sessions.

**Create/modify:**

- `docs/CORPUS_INGESTION.md`
- `scripts/ingestion-smoke-test.sh`
- `tests/ingest/test_ingestion_smoke.py` if useful

**Docs should cover:**

1. What ingestion is and is not.
2. Quickstart dry run.
3. Review/import workflow.
4. JSONL schemas.
5. Recipes.
6. Safety/trust/source refs.
7. Refresh/staleness.
8. Retrieval evals.
9. Troubleshooting noisy records.

**Smoke test:**

```bash
#!/usr/bin/env bash
set -euo pipefail
TMP_HOME="$(mktemp -d)"
TMP_OUT="$(mktemp -d)"
uv run continuity-ingest run tests/fixtures/ingestion/simple_docs --recipe docs --include README.md --policy safe-auto --output "$TMP_OUT"
uv run continuity-ingest validate-import "$TMP_OUT/approved-records.jsonl" --evals "$TMP_OUT/retrieval-evals.jsonl" --report "$TMP_OUT/temp-eval-report.jsonl"
uv run continuity-ingest import "$TMP_OUT/approved-records.jsonl" --apply --db-path "$TMP_HOME/continuity.db"
uv run continuity-ingest eval "$TMP_OUT/retrieval-evals.jsonl" --db-path "$TMP_HOME/continuity.db"
```

**Acceptance:** A new user can run the smoke test without touching their real Hermes DB.

---

## Milestone 14: Full quality gate and packaging

**Objective:** Ensure the new subsystem is production-quality enough for the repo.

**Steps:**

1. Run:
   ```bash
   cd /root/hermes-continuity-memory
   uv run ruff format --check .
   uv run ruff check .
   uv run pytest tests/ -q
   python -m compileall continuity tests
   ./scripts/ingestion-smoke-test.sh
   uv build
   ```
2. Inspect wheel contents and ensure ingestion package files are included.
3. Run existing demo retrieval smoke if still present:
   ```bash
   ./scripts/demo-retrieval.sh
   ```
4. Update README if appropriate.
5. Commit in logical milestone commits.

**Acceptance:** Existing continuity behavior remains intact and ingestion is packaged/tested.

---

## Recommended Build Order Summary

1. **Models/JSONL**: stable intermediate schema.
2. **Inventory**: local file discovery.
3. **Parse/segment**: Markdown/text to segments.
4. **Pipeline artifacts**: dry-run output directory.
5. **Validation/safety**: trust defaults, source refs, secret/injection checks.
6. **Deterministic extractors**: project capsule/procedure/eval basics.
7. **Dedupe/review**: prevent memory spam.
8. **Importer**: approved candidates into existing continuity DB.
9. **CLI**: staged commands and `run` command.
10. **Eval runner**: prove retrieval quality.
11. **LLM extractor**: optional, injected/testable.
12. **Refresh report**: source hash lifecycle foundation.
13. **Docs/smoke**: user-facing workflow.
14. **Quality gate/package**: full tests/build.

---

## Do Not Do First

Avoid these until the MVP is stable:

- PDF parsing
- web crawling
- Notion/GitHub/email connectors
- rich TUI
- auto skill creation
- complex contradiction detection
- raw chunk runtime injection
- vector-only dedupe as required behavior
- changing core retrieval scoring broadly

---

## First Session Starting Point

If a future session asks to begin implementation, start with Milestone 0 and Milestone 1 only:

```bash
cd /root/hermes-continuity-memory
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/ -q
python -m compileall continuity tests
```

Then create:

```text
continuity/ingest/__init__.py
continuity/ingest/models.py
continuity/ingest/jsonl.py
tests/ingest/test_models.py
tests/ingest/test_jsonl.py
```

Do not write connector/parser/extractor code until models and JSONL tests pass.
