# Context Partitions for Corpus Ingestion and Retrieval Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add generic, opaque context labels and partition-aware retrieval/import safeguards so large high-collision corpora such as OpenBSD and Linux manpages, customer-specific docs, or language-specific API references can coexist without domain-specific retrieval code or graph pollution.

**Architecture:** Introduce a small generic context-label model that treats labels as arbitrary key/value strings plus generic policies: match, conflict, missing, partition, preference, identity, and comparison. Propagate those labels from ingestion inputs through JSONL artifacts, review, import, final records, retrieval scoring, debug output, evals, and association graph traversal. Keep domain knowledge in corpus configuration, CLI-provided labels, source metadata, review artifacts, and fixtures; keep runtime code limited to generic label comparison and safety mechanics.

**Tech Stack:** Python stdlib, SQLite/FTS5, existing ContinuityStore/ContextRecord models, existing ingestion JSONL artifacts, pytest, ruff, compileall. No required hosted LLMs. Optional label inference can exist later but must be disabled by default and reviewable.

---

## Background

The current corpus ingestion pipeline is review-first and can already produce machine-readable scale stats, run validation through the runtime `ContinuityRetriever`, and import approved candidates without creating association edges by default. That is a good base, but it is not enough for full high-collision corpora.

The motivating example is manpages:

- `ifconfig(8)` on OpenBSD and Linux share names, sections, commands, terms, and many query tokens.
- Their semantics diverge in ways that matter operationally.
- A vector model or FTS query can easily consider both relevant.
- If both are imported as ordinary corpus records, retrieval may inject the wrong operating-system answer or association traversal may cross-link the two corpora.

The same problem appears outside operating systems:

- Acme and Globex have similar rollout-plan templates but different deployment rules.
- Python and Rust docs may share function names like `map`, `filter`, or `Result` but require different answers.
- Product versions, cloud providers, hardware platforms, customer environments, regulatory regimes, or forks may all create near-duplicate but context-dependent facts.

The user explicitly does **not** want an OS-specific special case or a per-domain schema hairball. The mechanism must be generic.

---

## Stress-Tested Design Conclusion

### Core idea

Use **opaque context labels** stored with records and passed into retrieval.

Example labels:

```json
{"os": "openbsd", "manual_section": "8", "command": "ifconfig"}
{"os": "linux", "manual_section": "8", "command": "ifconfig"}
{"customer": "acme", "document_family": "rollout-plan"}
{"customer": "globex", "document_family": "rollout-plan"}
{"language": "rust", "symbol": "map"}
{"language": "python", "symbol": "map"}
```

Retrieval code must not know what `os`, `customer`, or `language` means. It only understands key/value comparison:

- same key + same value = compatible match;
- same key + different value = conflict;
- missing key on one side = unknown;
- exact matching labels can boost ranking;
- conflicts on partition labels can reject or strongly downrank;
- conflicts on soft/preference labels can downrank but not reject;
- explicit comparison intent can allow conflicts while marking them as comparison results.

### Why this does not become domain-schema sprawl

The only generic schema is:

```json
{
  "labels": {"key": "value"},
  "partition_keys": ["key"],
  "soft_keys": ["key"],
  "identity_keys": ["key"],
  "source": "cli|profile|path|parser|extractor|review|runtime",
  "confidence": 0.0
}
```

Everything else is data. A manpage import may choose `os` and `manual_section`; a customer-doc import may choose `customer`; a language-doc import may choose `language`. Runtime comparison remains generic.

### Critical safety rule

For high-collision corpora, unknown context is not neutral. If a record is marked as partitioned/high-collision and a query lacks the relevant partition label, the retriever should either:

1. return no answer and report `missing_partition_context`, or
2. return a small set of clearly labeled ambiguous alternatives if the caller/tool is explicitly in debug/search mode.

It should not silently choose OpenBSD or Linux because one scored slightly higher.

---

## Failure Modes and Stress Tests

### 1. Ambiguous exact-name collision

**Scenario:** Two records both describe `ifconfig` with labels `os=openbsd` and `os=linux`.

**Query:** `how do I configure an alias with ifconfig?`

**Risk:** FTS/vector retrieves both; reranker may choose one arbitrarily.

**Expected behavior:** If no query/session label anchors `os`, records with partition key `os` should be withheld or surfaced as ambiguous in debug/search output with `missing_partition_context`.

### 2. Anchored query

**Query:** `on OpenBSD how do I configure an alias with ifconfig?`

**Expected behavior:** Query label extraction or explicit tool args produce `os=openbsd`; OpenBSD record gets `context_label_match:os=openbsd`; Linux record is rejected/cut as `context_label_conflict:os`.

### 3. Explicit comparison query

**Query:** `compare OpenBSD and Linux ifconfig alias syntax`

**Risk:** A naive conflict gate rejects one side and prevents comparison.

**Expected behavior:** Comparison intent allows conflicting `os` labels and marks results as `comparison_candidate`; ranking should prefer one or more records per conflicting value rather than collapsing to one winner.

### 4. Missing labels on legacy records

**Scenario:** Existing records have no labels.

**Risk:** New gate either rejects all old data or lets old unlabeled data contaminate high-collision retrieval.

**Expected behavior:** Missing labels are `unknown`, not conflict. For normal low-collision records they behave as today. For high-collision partitioned corpus records, missing query labels are conservative. Existing manual/explicit memories are not penalized merely for lacking labels.

### 5. Label overuse

**Scenario:** User imports every corpus with many partition keys: `os`, `version`, `arch`, `locale`, `package`, `source_tree`, `manual_section`.

**Risk:** Retrieval becomes too strict and misses useful facts.

**Expected behavior:** Only keys declared as `partition_keys` are hard gates. Other labels are soft boosts or identity/dedupe keys. Docs must warn that partition keys should be reserved for dimensions where wrong-context facts are actively harmful.

### 6. Label underuse

**Scenario:** Import uses labels but declares none as partition keys.

**Risk:** Labels are only weak ranking hints; collisions still leak.

**Expected behavior:** Ingestion stats and validate-import should report high collision risk: many near-duplicate candidates sharing identity keys/title/entities but differing label values without partition protection.

### 7. User asks for all contexts

**Query:** `show me all ifconfig variants we know about`

**Risk:** Gate rejects non-current contexts.

**Expected behavior:** Explicit enumeration/comparison intent should allow cross-partition retrieval but preserve labels in output and debug reasons.

### 8. Association graph leakage

**Scenario:** `ifconfig(openbsd)` and `ifconfig(linux)` have tag overlap and semantic edge. Query anchors OpenBSD, direct seed activates Linux neighbor through graph.

**Expected behavior:** Edge creation can either avoid cross-partition edges by default or store them as `cross_context_similarity`; traversal must cut conflicting neighbors unless comparison intent is active. Debug output should show `cut_neighbors.reason = context_label_conflict`.

### 9. Dynamic expansion leakage

**Scenario:** Query `OpenBSD network alias` retrieves OpenBSD candidate; expansion term `ifconfig` pulls Linux candidate.

**Expected behavior:** Expanded candidates still pass context compatibility gates. Expansion cannot override conflicts.

### 10. LLM/extractor hallucinated labels

**Scenario:** LLM labels a Linux manpage as `os=openbsd`.

**Risk:** Wrong labels become worse than no labels.

**Expected behavior:** Run-level CLI/profile labels have higher authority than extractor labels. Extractor-inferred labels are low-confidence, review-visible, and cannot override explicit source/run labels unless reviewer applies a correction.

### 11. Path-derived labels are brittle

**Scenario:** `/tmp/openbsd-man/man8/ifconfig.8` vs `/tmp/linux/man8/ifconfig.8` path inference works locally but is not universal.

**Expected behavior:** Path inference is optional and transparent. The robust path is explicit CLI/profile labels; inferred labels must appear in artifacts with source and confidence.

### 12. Version drift

**Scenario:** OpenBSD 7.5 and 7.6 docs both exist.

**Risk:** `os=openbsd` match is too broad.

**Expected behavior:** `os=openbsd` can be a partition key and `version=7.6` can be a soft key or partition key depending on import policy. Query/session label `version=7.6` boosts/restricts accordingly; missing version should not reject if `version` is soft.

### 13. Retrieval debug opacity

**Risk:** Users cannot understand why a record was withheld.

**Expected behavior:** `continuity_debug_retrieval` includes query labels, record labels, label policy, match/conflict/missing counts, and rejection/cut reasons.

### 14. Scale/performance

**Scenario:** 10k-100k corpus-derived records with labels.

**Risk:** Per-candidate JSON parsing and graph traversal become expensive.

**Expected behavior:** Initial implementation may use JSON in `quality`/metadata for compatibility; add a simple indexed table or generated indexes only after tests show need. Keep label comparison local to candidate sets, not full corpus scans.

---

## Non-Goals

- Do not add OS-specific logic to retrieval.
- Do not require a universal ontology or domain schema registry.
- Do not require LLM-based query planning.
- Do not make corpus import directly mutate live memory without explicit `--apply`.
- Do not create association edges during corpus import by default.
- Do not solve all raw manpage parsing/extraction in the same first milestone; implement context partitions first, then manpage rendering/extraction.
- Do not force all existing memories to have labels.

---

## Proposed Data Model

### Canonical context payload

Use a stable nested object under existing JSON-friendly fields first; add first-class columns only if performance requires it.

```json
{
  "context": {
    "labels": {
      "os": "openbsd",
      "manual_section": "8",
      "command": "ifconfig"
    },
    "partition_keys": ["os"],
    "soft_keys": ["version", "arch"],
    "identity_keys": ["command", "manual_section"],
    "source": {
      "os": "cli",
      "manual_section": "parser",
      "command": "parser"
    },
    "confidence": {
      "os": 1.0,
      "manual_section": 0.95,
      "command": 0.95
    },
    "collision_risk": "high"
  }
}
```

### Where it lives at each stage

- `SourceDocument.metadata["context"]`
- `ParsedDocument.metadata["context"]`
- `SourceSegment.metadata["context"]`
- `SourceRef.metadata["context"]`
- `CandidateRecord.ingestion["context"]`
- final `ContextRecord.quality["context"]` initially, because `ContextRecord` already persists `quality_json` and migration cost is low.

Later, if needed, add a normalized `context_record_labels` table:

```sql
CREATE TABLE context_record_labels (
  record_id TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  role TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 1.0,
  source TEXT,
  PRIMARY KEY(record_id, key),
  FOREIGN KEY(record_id) REFERENCES context_records(id) ON DELETE CASCADE
);
CREATE INDEX context_record_labels_lookup ON context_record_labels(key, value, role);
```

Do not start with this table unless profiling/debugging proves JSON extraction is too slow.

---

## Query-Time Semantics

### Query context sources

Query labels can come from:

1. explicit tool/API args later, e.g. `continuity_search(query, context={"os":"openbsd"})`;
2. current provider/session config, e.g. active project/profile labels;
3. light generic query parsing configured by data, not hardcoded domain semantics;
4. debug CLI args for ingestion eval cases;
5. comparison intent detection from generic words: `compare`, `difference`, `vs`, `versus`, `between`, `all variants`.

The first implementation should support explicit args/config/eval labels first. Light query parsing can wait or be very limited and transparent.

### Compatibility result

Add a small pure module, for example `continuity/context_labels.py`, with pure functions:

```python
@dataclass(frozen=True)
class ContextLabelSet:
    labels: dict[str, str]
    partition_keys: frozenset[str] = frozenset()
    soft_keys: frozenset[str] = frozenset()
    identity_keys: frozenset[str] = frozenset()
    collision_risk: str = "normal"

@dataclass(frozen=True)
class ContextCompatibility:
    matched: dict[str, str]
    conflicts: dict[str, tuple[str, str]]
    missing_query_keys: frozenset[str]
    missing_record_keys: frozenset[str]
    hard_conflict: bool
    missing_required_partition: bool
    comparison_allowed: bool
    score_adjustment: float
    reasons: tuple[str, ...]
```

Generic rules:

- hard conflict when a key is in record/query partition keys and both sides have different values;
- missing required partition when record has `collision_risk=high`, has partition keys, and query lacks those keys, unless debug/search/comparison mode allows ambiguity;
- soft conflict applies negative score but not rejection;
- identity-key matches can improve dedupe and debug grouping but should not be enough to override partition conflict;
- comparison intent sets `comparison_allowed=True` and suppresses hard rejection while preserving conflict reasons.

---

## Implementation Strategy

Implement in small commits. Each phase starts with failing tests and ends with a clean quality gate appropriate to touched files.

## Phase 0: Freeze high-collision behavior with failing tests

### Task 0.1: Add generic label compatibility unit tests

**Objective:** Define the pure generic semantics before touching retrieval.

**Files:**
- Create: `tests/test_context_labels.py`
- Create: `continuity/context_labels.py`

**Test cases:**

```python
def test_partition_label_match_is_compatible(): ...
def test_partition_label_conflict_is_hard_conflict(): ...
def test_missing_partition_on_high_collision_record_is_required_context_missing(): ...
def test_soft_label_conflict_downranks_without_rejecting(): ...
def test_comparison_intent_allows_partition_conflict_with_reason(): ...
def test_opaque_keys_are_not_special_cased(): ...
```

**Verification:**
- Run: `uv run pytest tests/test_context_labels.py -q`
- Expected before implementation: FAIL because module does not exist.

### Task 0.2: Add retrieval fixture for OpenBSD/Linux-style collision without OS-specific code

**Objective:** Prove two records with the same command/title are separated solely by generic labels.

**Files:**
- Modify: `tests/test_retrieval.py` or create `tests/test_retrieval_context_labels.py`

**Fixture records:**
- `ifconfig alias syntax` with `quality.context.labels.os=openbsd`, `partition_keys=["os"]`, `identity_keys=["command"]`, `collision_risk=high`.
- Same title/entities with `os=linux`.

**Assertions:**
- query labels `{"os":"openbsd"}` select OpenBSD and reject/cut Linux;
- query labels `{"os":"linux"}` select Linux and reject/cut OpenBSD;
- no query labels select neither in normal provider mode or mark both ambiguous in debug mode;
- comparison intent selects both with conflict reasons.

### Task 0.3: Add non-OS fixtures to prevent overfitting

**Objective:** Prove same machinery works for customer and language collisions.

**Files:**
- Modify: `tests/test_retrieval_context_labels.py`

**Scenarios:**
- Acme vs Globex rollout docs, partition key `customer`.
- Rust vs Python `map` docs, partition key `language`.

**Acceptance:**
- No test names or production code require OS-specific helpers.
- Tests fail until generic implementation exists.

---

## Phase 1: Add context-label model and propagation helpers

### Task 1.1: Implement `continuity/context_labels.py`

**Objective:** Add pure parsing/normalization/comparison helpers.

**Files:**
- Create: `continuity/context_labels.py`
- Test: `tests/test_context_labels.py`

**Implementation notes:**
- Normalize keys/values to lowercase trimmed strings by default.
- Allow safe characters: letters, numbers, `.`, `_`, `-`, `:`.
- Drop empty labels.
- Coerce list-like policy fields to frozensets.
- Keep functions pure and dependency-light.

**Verification:**
- Run: `uv run pytest tests/test_context_labels.py -q`
- Expected: PASS.

### Task 1.2: Add context extraction helper for ContextRecord

**Objective:** Make retrieval code read labels from `record.quality["context"]` without knowing ingestion internals.

**Files:**
- Modify: `continuity/context_labels.py`
- Test: `tests/test_context_labels.py`

**Functions:**
- `context_from_mapping(mapping: dict[str, object]) -> ContextLabelSet`
- `context_from_record(record: ContextRecord) -> ContextLabelSet`
- `context_to_mapping(label_set: ContextLabelSet) -> dict[str, object]`

**Acceptance:**
- Missing quality/context returns empty label set.
- Malformed values are ignored conservatively, not crashed during retrieval.

---

## Phase 2: Wire labels through ingestion artifacts

### Task 2.1: Add CLI parsing for explicit run labels

**Objective:** Let users mark a whole ingestion run with generic labels.

**Files:**
- Modify: `continuity/ingest/cli.py`
- Modify: `continuity/ingest/pipeline.py`
- Test: `tests/ingest/test_ingest_cli.py` or `tests/ingest/test_ingest_pipeline.py`

**CLI proposal:**

```bash
continuity-ingest run /path/to/corpus \
  --context os=openbsd \
  --context version=7.6 \
  --partition-key os \
  --soft-key version \
  --identity-key command \
  --collision-risk high
```

**Acceptance:**
- Multiple `--context key=value` args merge.
- Invalid labels fail early with a clear error.
- Labels appear in `manifest.json` config hash and artifacts.

### Task 2.2: Propagate run context into sources and segments

**Objective:** Ensure every source/segment carries inherited labels.

**Files:**
- Modify: `continuity/ingest/connectors.py`
- Modify: `continuity/ingest/pipeline.py`
- Test: `tests/ingest/test_ingest_large_corpus.py`

**Acceptance:**
- `inventory.jsonl` source rows include `metadata.context`.
- `segments.jsonl` segment rows include `metadata.context`.
- Existing tests without labels remain unchanged except new optional fields in JSON.

### Task 2.3: Propagate context into candidates and source refs

**Objective:** Imported candidates retain source/run labels and provenance.

**Files:**
- Modify: `continuity/ingest/extractors.py`
- Modify: `continuity/ingest/llm_extractors.py`
- Modify: `continuity/ingest/validation.py` if normalization currently rebuilds candidates
- Test: `tests/ingest/test_ingest_golden_corpus.py`

**Acceptance:**
- Candidate has `ingestion.context`.
- Candidate `source_refs[*].metadata.context` is preserved where available.
- LLM-provided labels cannot override explicit run labels unless stored separately as low-confidence inferred labels.

### Task 2.4: Extend ingestion stats with context diagnostics

**Objective:** Make label coverage and collision risk visible before import.

**Files:**
- Modify: `continuity/ingest/reports.py`
- Test: `tests/ingest/test_ingest_large_corpus.py`

**Add stats:**

```json
"context": {
  "sources_with_context": 200,
  "segments_with_context": 600,
  "candidates_with_context": 201,
  "labels_by_key": {"os": {"openbsd": 200}},
  "partition_keys": {"os": 201},
  "collision_risk": {"high": 201},
  "missing_partition_key_candidates": 0
}
```

**Acceptance:**
- Large synthetic corpus can assert counts.
- Missing partition labels are visible and not silently ignored.

---

## Phase 3: Import labels into final records

### Task 3.1: Preserve candidate context in `ContextRecord.quality`

**Objective:** Make imported corpus labels available to runtime retrieval.

**Files:**
- Modify: `continuity/ingest/importer.py`
- Test: `tests/ingest/test_ingest_importer.py`

**Implementation:**
- In `candidate_to_context_record`, merge `candidate.ingestion["context"]` into `record.quality["context"]` after `enrich_record_metadata(record)`.
- Do not overwrite existing quality warnings/metadata.
- Include context payload in `source_hash` or imported record ID only if needed for correct update semantics. Prefer including partition labels in source hash initially so changing context on a candidate updates the imported record rather than silently treating it as unchanged.

**Acceptance:**
- Imported record has `quality["context"]`.
- Existing importer tests still pass.
- `create_associations=False` remains unchanged.

### Task 3.2: Validate import with label-aware retrieval evals

**Objective:** Allow eval cases to pass query labels/comparison intent.

**Files:**
- Modify: `continuity/ingest/eval.py`
- Test: `tests/ingest/test_ingest_eval.py`

**Eval schema extension:**

```json
{
  "query": "how does ifconfig alias syntax work?",
  "query_context": {"labels": {"os": "openbsd"}},
  "comparison_intent": false,
  "expected_record_ids": ["..."],
  "forbidden_record_ids": ["..."]
}
```

**Acceptance:**
- `validate-import` can prove OpenBSD-labeled evals forbid Linux records.
- Old eval cases without context still work.

---

## Phase 4: Label-aware direct retrieval

### Task 4.1: Add query context parameters to retriever search/debug

**Objective:** Thread context into retrieval without changing default behavior.

**Files:**
- Modify: `continuity/retrieval.py`
- Modify: `continuity/tools.py`
- Modify: `continuity/__init__.py`
- Test: `tests/test_tools_phase4.py`
- Test: `tests/test_retrieval_context_labels.py`

**API shape:**

```python
ContinuityRetriever.search(
    query,
    limit=5,
    scope_project=None,
    include_stale=False,
    query_context=None,
    comparison_intent=False,
)
```

Tool args can accept:

```json
{
  "query": "ifconfig alias syntax",
  "context": {"labels": {"os": "openbsd"}},
  "comparison_intent": false
}
```

**Acceptance:**
- Defaults are backward-compatible.
- Debug output includes query context even when empty.

### Task 4.2: Apply context compatibility as a retrieval gate

**Objective:** Reject or downrank candidates based on generic label comparison.

**Files:**
- Modify: `continuity/retrieval.py`
- Test: `tests/test_retrieval_context_labels.py`

**Ordering:**
- Score lexical/vector candidates as today.
- Before reranking/graph activation, compute compatibility for each candidate.
- Reject hard conflicts unless comparison intent is active.
- Reject `missing_required_partition` in normal mode.
- Add score adjustments for matches/soft conflicts.
- Add reasons: `context_label_match:<key>`, `context_label_conflict:<key>`, `missing_partition_context:<key>`, `comparison_context_conflict:<key>`.

**Acceptance:**
- OpenBSD/Linux, Acme/Globex, Python/Rust tests pass.
- Existing retrieval tests still pass.

### Task 4.3: Add ambiguity/debug mode behavior

**Objective:** Let diagnostics show why ambiguous records were withheld.

**Files:**
- Modify: `continuity/retrieval.py`
- Modify: `continuity/tools.py`
- Test: `tests/test_tools_phase4.py`

**Acceptance:**
- `continuity_debug_retrieval` shows selected and rejected candidates with label compatibility details.
- A no-context high-collision query shows records rejected for `missing_partition_context` instead of silently returning none.

---

## Phase 5: Association graph guard

### Task 5.1: Cut conflicting graph neighbors during traversal

**Objective:** Prevent graph activation from crossing partition conflicts.

**Files:**
- Modify: `continuity/retrieval.py`
- Test: `tests/test_retrieval_context_labels.py`

**Acceptance:**
- If OpenBSD direct seed has an association edge to Linux neighbor, OpenBSD query cuts Linux neighbor with `context_label_conflict`.
- Comparison intent allows traversal but records conflict reasons.

### Task 5.2: Guard association edge creation for future direct writes

**Objective:** Prevent newly created edges from connecting conflicting partition labels by default.

**Files:**
- Modify: `continuity/store.py` or `continuity/association.py`
- Test: `tests/test_association_graph.py` or existing association tests

**Acceptance:**
- `store.upsert_record(..., create_associations=True)` does not create ordinary `semantic_similarity`/`tag_overlap` edges across hard partition conflicts.
- Optional `cross_context_similarity` edges may be created only if explicitly enabled later; do not add that in the first implementation unless needed.
- Corpus importer still uses `create_associations=False`.

### Task 5.3: Include context in association debug output

**Objective:** Make graph cuts explainable.

**Files:**
- Modify: `continuity/retrieval.py`
- Test: `tests/test_tools_phase4.py`

**Acceptance:**
- `activation_trace.cut_neighbors[*].reason` can be `context_label_conflict`.
- Trace includes conflicting key and values.

---

## Phase 6: High-collision corpus eval suite

### Task 6.1: Add synthetic high-collision fixture corpus

**Objective:** Stress the entire ingestion/import/validate path with multiple generic partition domains.

**Files:**
- Create: `tests/fixtures/ingestion/high_collision_corpus/`
- Create: `tests/ingest/test_ingest_context_partitions.py`

**Corpus contents:**
- `openbsd/man8/ifconfig.txt`
- `linux/man8/ifconfig.txt`
- `acme/rollout.md`
- `globex/rollout.md`
- `rust/map.md`
- `python/map.md`

Use rendered/plain text fixtures; do not require real `man`/`mandoc` yet.

**Acceptance:**
- Ingestion with explicit labels creates candidates with context.
- `validate-import` passes positive/forbidden evals.
- No live DB mutation occurs.

### Task 6.2: Add ambiguous-query eval cases

**Objective:** Ensure no-context queries do not return arbitrary wrong-context facts.

**Files:**
- Modify: `tests/ingest/test_ingest_context_partitions.py`

**Acceptance:**
- Ambiguous query with no labels fails if either conflicting record is selected as a normal answer.
- Debug report explains `missing_partition_context`.

### Task 6.3: Add comparison eval cases

**Objective:** Ensure comparison queries can intentionally cross partitions.

**Acceptance:**
- Comparison eval expects both OpenBSD and Linux records.
- Forbidden list is empty or only excludes unrelated contexts.
- Report shows comparison reasons.

---

## Phase 7: Manpage connector/renderer after context partition foundation

Do this after labels work, because manpage ingestion without context partitions is likely to create confusing records.

### Task 7.1: Extend local connector source-type detection for manpages

**Objective:** Treat `.1`, `.2`, ..., `.9`, and gzipped variants as manpage sources.

**Files:**
- Modify: `continuity/ingest/connectors.py`
- Test: `tests/ingest/test_ingest_connectors.py`

**Acceptance:**
- `ifconfig.8` and `ifconfig.8.gz` are inventoried as `manpage`.
- Binary files remain excluded.

### Task 7.2: Add renderer abstraction

**Objective:** Render raw roff/mdoc/gzipped manpages to UTF-8 text before `ManPageParser`.

**Files:**
- Create: `continuity/ingest/manpage_render.py`
- Modify: `continuity/ingest/parsers.py` or pipeline parser selection
- Test: `tests/ingest/test_ingest_manpages.py`

**Renderer strategy:**
- Prefer `mandoc -T utf8` when available.
- Fallback to `man` only if it can render a specific file deterministically.
- If no renderer is available, reject with a structured reason instead of crashing.

**Acceptance:**
- Tests use a fake renderer or monkeypatch, not system `mandoc`.
- Actual environment can report renderer availability in stats.

### Task 7.3: Preserve manpage identity labels

**Objective:** Extract generic labels such as command/page name and manual section.

**Files:**
- Modify: `continuity/ingest/parsers.py`
- Modify: `continuity/ingest/segmenters.py` if needed
- Test: `tests/ingest/test_ingest_manpages.py`

**Labels:**
- `command=ifconfig` or `page=ifconfig`
- `manual_section=8`

These are opaque labels. Retrieval does not know their meaning.

---

## Phase 8: Documentation and UX

### Task 8.1: Update corpus ingestion docs

**Objective:** Document context labels as the recommended way to ingest high-collision corpora.

**Files:**
- Modify: `docs/CORPUS_INGESTION.md`
- Modify: `README.md`

**Include examples:**

```bash
continuity-ingest run /corpora/openbsd-man \
  --recipe openbsd-manpages \
  --context os=openbsd \
  --context version=7.6 \
  --partition-key os \
  --soft-key version \
  --collision-risk high \
  --policy require-review \
  --output .ingestion/openbsd-man
```

```bash
continuity-ingest run /corpora/linux-man \
  --recipe manpage \
  --context os=linux \
  --partition-key os \
  --collision-risk high \
  --policy require-review \
  --output .ingestion/linux-man
```

Explain that `os` is just an example key, not hardcoded.

### Task 8.2: Update configuration docs

**Objective:** Explain retrieval behavior and tuning without requiring domain schemas.

**Files:**
- Modify: `docs/CONFIGURATION.md`

**Acceptance:**
- Docs explain partition vs soft vs identity keys.
- Docs explain ambiguous query behavior.
- Docs explain comparison intent.

### Task 8.3: Add release checklist item

**Objective:** Ensure context partition behavior is part of alpha readiness.

**Files:**
- Modify: `docs/RELEASE.md`

**Acceptance:**
- Release gate includes high-collision ingestion/retrieval tests.

---

## Phase 9: Scale and observability

### Task 9.1: Add a synthetic scale stress test script

**Objective:** Generate many near-duplicate labeled docs and validate stats/retrieval without live import.

**Files:**
- Create: `scripts/stress-context-partitions.py`
- Test: optional smoke test or docs invocation

**Behavior:**
- Generate N commands across M partitions.
- Ingest review-first into temp dir.
- Validate temp import with positive/forbidden evals.
- Print label coverage, candidate counts, ambiguity counts, and retrieval failure count.

### Task 9.2: Add status/debug surface for label counts

**Objective:** Make live DB label coverage visible.

**Files:**
- Modify: `continuity/tools.py`
- Modify: `continuity/__init__.py`
- Test: `tests/test_provider_phase1.py`

**Acceptance:**
- `continuity_status` reports counts of records with context labels and high-collision records.
- No full table scan if DB becomes large; OK to start simple if current store lacks label indexes.

---

## Acceptance Criteria

1. Generic context labels can be represented, normalized, serialized, and compared without domain-specific code.
2. Ingestion CLI supports explicit `--context key=value`, `--partition-key`, `--soft-key`, `--identity-key`, and `--collision-risk` options.
3. Context labels propagate through `inventory.jsonl`, `segments.jsonl`, candidate records, source refs, imported final records, and ingestion stats.
4. `validate-import` can run label-aware eval cases through the real `ContinuityRetriever` path.
5. Direct retrieval rejects hard partition conflicts and missing required partition context for high-collision records.
6. Comparison intent can intentionally retrieve conflicting partition records with clear reasons.
7. Association graph traversal cuts conflicting neighbors in normal retrieval.
8. Future association edge creation avoids ordinary edges across hard partition conflicts.
9. Tests prove the same generic mechanism handles OpenBSD/Linux, Acme/Globex, and Rust/Python collision fixtures.
10. No production retrieval code special-cases `os`, `openbsd`, `linux`, `customer`, `acme`, `globex`, `language`, `rust`, or `python`.
11. Debug output explains label matches, conflicts, missing context, comparison allowance, and graph cuts.
12. Existing no-label memories continue to retrieve as before unless they are explicitly marked high-collision/partitioned corpus records.
13. Full quality gate passes:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/ingest -q
uv run pytest tests/ -q
python -m compileall continuity tests scripts
./scripts/demo-retrieval.sh --quiet
./scripts/smoke-test.sh
uv build
```

---

## Recommended Commit Boundaries

1. `test: add context label compatibility contract`
2. `feat: add generic context label model`
3. `feat: propagate ingestion context labels`
4. `feat: preserve corpus context on import`
5. `feat: add label-aware retrieval gates`
6. `feat: guard association graph by context labels`
7. `test: add high-collision ingestion eval corpus`
8. `feat: add manpage source detection and rendering`
9. `docs: document context partitions for corpus ingestion`
10. `test: add context partition scale stress script`

---

## Open Design Questions to Resolve During Implementation

1. Should missing partition context return no records in all normal searches, or should `continuity_search` return ambiguous alternatives while provider prefetch returns none? Recommended: provider prefetch returns none; debug/search can show ambiguous withheld candidates.
2. Should query label inference from text be implemented now? Recommended: not initially except explicit tool/eval args. Add transparent inference later.
3. Should labels live in `quality.context` permanently? Recommended: start there for migration simplicity, add indexed table only if scale tests show need.
4. Should comparison intent be inferred from query text? Recommended: support explicit bool first; add simple generic text detector later with tests.
5. Should cross-context similarity edges be stored? Recommended: not for alpha. Cut/avoid ordinary edges first.
6. Should partition labels affect imported record IDs? Recommended: include labels in source hash/update semantics; only include in stable ID if collisions cause record overwrites.

---

## First Implementation Slice

The smallest useful slice is:

1. `continuity/context_labels.py` pure model + tests.
2. Retrieval tests with manually constructed `ContextRecord.quality.context` labels.
3. Label-aware direct retrieval gate with debug reasons.
4. Association traversal cut test.

This proves the core safety behavior before touching ingestion CLI or manpage rendering. After that, wire ingestion propagation and validate-import evals.
