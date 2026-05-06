# Continuity Write-Path Quality Gates Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Strengthen continuity memory at write time so bad or weak records are rejected, reviewed, enriched, or labeled before they can pollute retrieval, vectors, dynamic expansion, or association graph edges.

**Architecture:** Add a shared write-time quality/enrichment layer that every record producer uses before storage. Keep the current `metadata_extraction.extract_metadata()` as a conservative literal extractor, but wrap it with record-level normalization, metadata-quality assessment, derived facets, sparse-metadata warnings, and admission decisions. Do not hardcode private/user-specific domain knowledge; use literal evidence, existing corpus metadata, and inspectable quality rules.

**Tech Stack:** Python stdlib dataclasses, existing continuity `ContextRecord`/`CandidateRecord`, SQLite store, pytest, ruff.

---

## Design Principles

1. **Bad records are worse than sparse records.** Reject or review records that look like examples, instructions, summaries of syntax, or dumps.
2. **Literal extractor stays literal.** Do not make `metadata_extraction.py` infer private/domain semantics. Add enrichment/quality around it.
3. **Every write path must share the same gate.** Manual `continuity_add`, built-in memory mirror, session extraction, ingestion importer, and future LLM distillation should all pass through one shared record-preparation layer.
4. **Sparse explicit memories may still be valuable.** Explicit user/manual memories should usually be stored but labeled with metadata quality warnings; lower-trust corpus/LLM records should require review when sparse.
5. **Quality must be inspectable.** Debug tools should show derived metadata/facets/warnings so retrieval failures can be traced back to write-time quality.
6. **No broad retrieval tuning in this pass.** Only add retrieval-facing fields/metadata needed to make write-time quality visible and enforceable.

---

## Target Data Flow

```text
producer-specific raw record/candidate
  -> sanitize/redact
  -> normalize supplied tags/entities
  -> literal metadata extraction from title/summary/details
  -> merge supplied + derived metadata
  -> compute derived facets from kind/scope/tags/entities/text
  -> score metadata quality
  -> decide: reject | pending_review | active_with_warnings | active_clean
  -> persist ContextRecord
  -> update FTS/vector indexes
  -> create association edges only when quality permits
```

---

## New Concepts

### MetadataQualityAssessment

A lightweight dataclass with:

```python
@dataclass(frozen=True)
class MetadataQualityAssessment:
    tag_count: int
    entity_count: int
    derived_tag_count: int
    derived_entity_count: int
    facets: tuple[str, ...]
    warnings: tuple[str, ...]
    reject: bool = False
    review_required: bool = False
    score: float = 1.0
```

Likely warnings:

- `sparse_metadata`
- `no_entities`
- `structural_tags_only`
- `generic_title`
- `unknown_or_empty_facets`
- `huge_entity_list`
- `example_like_source`
- `missing_source_ref`
- `low_information_summary`
- `llm_candidate_sparse_metadata`

### Storage location for quality info

Do **not** add a new DB table in the first pass unless needed. Store quality info in a compact JSON blob in `ContextRecord.details` only if details is empty? No — that pollutes prompt text and embedding text.

Better first-pass approach:

1. Add optional `metadata_json` column later? That is cleaner but larger.
2. For MVP, add `quality_tags` as normal tags? E.g. `quality:sparse-metadata`? This makes quality inspectable/searchable but can pollute retrieval.

Recommended: add a `metadata_json` / `quality_json` column to `context_records` in a schema migration. If avoiding schema change initially, put warnings in `record.sources[0].label` is bad. Prefer schema change.

Plan below uses a new `quality_json` column because this is core system behavior.

---

# Milestone 1: Add Record Quality Models and Pure Assessment Functions

## Task 1: Create write-time quality module skeleton

**Objective:** Add a pure module with dataclasses and no integration yet.

**Files:**
- Create: `continuity/record_quality.py`
- Test: `tests/test_record_quality.py`

**Step 1: Write failing tests**

Add `tests/test_record_quality.py`:

```python
from __future__ import annotations

from continuity.models import ContextRecord
from continuity.record_quality import assess_record_quality


def _record(**overrides) -> ContextRecord:
    values = {
        "id": "r_quality",
        "kind": "project_convention",
        "title": "Guard proxy uses ruff and pytest",
        "summary": "guard-proxy development uses ruff for linting and pytest for regression tests.",
        "tags": ["python", "testing"],
        "entities": ["guard-proxy", "ruff", "pytest"],
        "trust_level": "explicit_user",
    }
    values.update(overrides)
    return ContextRecord.new(**values)


def test_assess_record_quality_accepts_anchored_record() -> None:
    assessment = assess_record_quality(_record())

    assert assessment.reject is False
    assert assessment.review_required is False
    assert "sparse_metadata" not in assessment.warnings
    assert assessment.tag_count == 2
    assert assessment.entity_count == 3


def test_assess_record_quality_warns_for_sparse_explicit_record() -> None:
    assessment = assess_record_quality(
        _record(tags=["user_preference"], entities=[], kind="user_preference")
    )

    assert assessment.reject is False
    assert assessment.review_required is False
    assert "sparse_metadata" in assessment.warnings
    assert "no_entities" in assessment.warnings


def test_assess_record_quality_requires_review_for_sparse_corpus_record() -> None:
    assessment = assess_record_quality(
        _record(tags=[], entities=[], trust_level="corpus_distilled")
    )

    assert assessment.reject is False
    assert assessment.review_required is True
    assert "sparse_metadata" in assessment.warnings


def test_assess_record_quality_flags_huge_entity_list() -> None:
    assessment = assess_record_quality(
        _record(entities=[f"Entity {index}" for index in range(40)])
    )

    assert "huge_entity_list" in assessment.warnings
    assert assessment.review_required is True
```

**Step 2: Run test to verify failure**

Run:

```bash
uv run pytest tests/test_record_quality.py -q
```

Expected: FAIL because `continuity.record_quality` does not exist.

**Step 3: Implement minimal module**

Create `continuity/record_quality.py`:

```python
"""Write-time quality assessment for continuity records."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import ContextRecord

STRUCTURAL_TAGS = frozenset(
    {
        "built_in_memory",
        "memory_target:user",
        "memory_target:memory",
        "user_preference",
        "environment_fact",
        "project_convention",
        "lesson_learned",
        "decision",
        "active_project_state",
        "artifact_summary",
    }
)
REVIEW_TRUST_LEVELS = frozenset(
    {
        "corpus_distilled",
        "internet_distilled",
        "corpus_raw_summary",
        "candidate_unreviewed",
        "remote_untrusted",
        "session_extracted",
    }
)
GENERIC_TITLES = frozenset(
    {
        "overview",
        "notes",
        "memory",
        "record",
        "hermes user memory",
        "hermes global memory",
    }
)


@dataclass(frozen=True)
class MetadataQualityAssessment:
    tag_count: int
    entity_count: int
    derived_tag_count: int = 0
    derived_entity_count: int = 0
    facets: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    reject: bool = False
    review_required: bool = False
    score: float = 1.0


def assess_record_quality(
    record: ContextRecord,
    *,
    derived_tags: list[str] | None = None,
    derived_entities: list[str] | None = None,
    facets: list[str] | None = None,
) -> MetadataQualityAssessment:
    """Return a conservative write-time quality assessment for a record."""

    warnings: list[str] = []
    tags = [tag for tag in record.tags if tag]
    entities = [entity for entity in record.entities if entity]
    meaningful_tags = [tag for tag in tags if tag not in STRUCTURAL_TAGS]
    title = " ".join(record.title.casefold().split())
    summary_tokens = re.findall(r"[a-z0-9]+", record.summary.casefold())

    if not entities:
        warnings.append("no_entities")
    if not meaningful_tags and len(entities) < 1:
        warnings.append("sparse_metadata")
    if tags and not meaningful_tags:
        warnings.append("structural_tags_only")
    if title in GENERIC_TITLES:
        warnings.append("generic_title")
    if len(entities) > 24:
        warnings.append("huge_entity_list")
    if len(summary_tokens) < 6:
        warnings.append("low_information_summary")
    if not facets:
        warnings.append("unknown_or_empty_facets")

    unique_warnings = tuple(dict.fromkeys(warnings))
    review_required = bool(set(unique_warnings) & {"huge_entity_list"})
    if record.trust_level in REVIEW_TRUST_LEVELS and (
        "sparse_metadata" in unique_warnings or "unknown_or_empty_facets" in unique_warnings
    ):
        review_required = True

    score = max(0.0, round(1.0 - len(unique_warnings) * 0.12, 2))
    return MetadataQualityAssessment(
        tag_count=len(tags),
        entity_count=len(entities),
        derived_tag_count=len(derived_tags or []),
        derived_entity_count=len(derived_entities or []),
        facets=tuple(sorted(facets or [])),
        warnings=unique_warnings,
        reject=False,
        review_required=review_required,
        score=score,
    )
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_record_quality.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add continuity/record_quality.py tests/test_record_quality.py
git commit -m "feat: add continuity record quality assessment"
```

---

## Task 2: Add pure metadata enrichment function

**Objective:** Merge supplied metadata with literal extraction from title/summary/details.

**Files:**
- Modify: `continuity/record_quality.py`
- Test: `tests/test_record_quality.py`

**Step 1: Write failing tests**

Append:

```python
from continuity.record_quality import enrich_record_metadata


def test_enrich_record_metadata_merges_literal_entities_and_tags() -> None:
    record = _record(
        title="OpenBSD guard-proxy deployment",
        summary="guard-proxy uses tag:openbsd and rcctl restart during deployment.",
        tags=["deployment"],
        entities=[],
    )

    enriched, assessment = enrich_record_metadata(record)

    assert "deployment" in enriched.tags
    assert "openbsd" in enriched.tags
    assert "OpenBSD" in enriched.entities
    assert "guard-proxy" in enriched.entities
    assert assessment.derived_tag_count >= 1
    assert assessment.derived_entity_count >= 1


def test_enrich_record_metadata_deduplicates_case_insensitively() -> None:
    record = _record(
        title="OpenBSD OpenBSD",
        summary="OpenBSD uses tag:OpenBSD.",
        tags=["openbsd"],
        entities=["openbsd"],
    )

    enriched, _ = enrich_record_metadata(record)

    assert enriched.tags.count("openbsd") == 1
    assert len([entity for entity in enriched.entities if entity.casefold() == "openbsd"]) == 1
```

**Step 2: Run test to verify failure**

```bash
uv run pytest tests/test_record_quality.py -q
```

Expected: FAIL because `enrich_record_metadata` does not exist.

**Step 3: Implement enrichment**

In `record_quality.py`:

```python
from dataclasses import replace
from .metadata_extraction import extract_metadata


def enrich_record_metadata(record: ContextRecord) -> tuple[ContextRecord, MetadataQualityAssessment]:
    """Return record with literal metadata merged in plus a quality assessment."""

    text = "\n".join(part for part in [record.title, record.summary, record.details or ""] if part)
    extracted = extract_metadata(text)
    tags = _merge_tags(record.tags, list(extracted.tags))
    entities = _merge_entities(record.entities, list(extracted.entities))
    enriched = replace(record, tags=tags, entities=entities).with_embedding_text()
    assessment = assess_record_quality(
        enriched,
        derived_tags=list(extracted.tags),
        derived_entities=list(extracted.entities),
        facets=[],
    )
    return enriched, assessment


def _merge_tags(existing: list[str], derived: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for tag in [*existing, *derived]:
        normalized = tag.strip().lower().replace("_", "-")
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output


def _merge_entities(existing: list[str], derived: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for entity in [*existing, *derived]:
        normalized = " ".join(entity.split())
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            output.append(normalized)
    return output
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_record_quality.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add continuity/record_quality.py tests/test_record_quality.py
git commit -m "feat: enrich records with literal metadata before storage"
```

---

# Milestone 2: Persist Quality Metadata Without Polluting Retrieval Text

## Task 3: Add `quality_json` to ContextRecord and store schema

**Objective:** Store quality warnings/score/facets in DB without putting them into embedding text or FTS.

**Files:**
- Modify: `continuity/models.py`
- Modify: `continuity/store.py`
- Test: `tests/test_models.py`
- Test: `tests/test_store.py`

**Step 1: Write failing model test**

In `tests/test_models.py`, add:

```python
def test_context_record_round_trips_quality_metadata_without_embedding_pollution() -> None:
    record = ContextRecord.new(
        id="r_quality_meta",
        kind="project_convention",
        title="Quality metadata test",
        summary="Quality metadata is stored separately from embedding text.",
        tags=["quality"],
        entities=["quality metadata"],
        trust_level="explicit_user",
        quality={"warnings": ["sparse_metadata"], "score": 0.76, "facets": ["software_project"]},
    )

    payload = record.to_dict()
    restored = ContextRecord.from_dict(payload)

    assert restored.quality == {"warnings": ["sparse_metadata"], "score": 0.76, "facets": ["software_project"]}
    assert "sparse_metadata" not in (restored.embedding_text or "")
```

**Step 2: Run model test to verify failure**

```bash
uv run pytest tests/test_models.py::test_context_record_round_trips_quality_metadata_without_embedding_pollution -q
```

Expected: FAIL because `quality` arg/field does not exist.

**Step 3: Implement model field**

In `ContextRecord`, add:

```python
quality: dict[str, object] = field(default_factory=dict)
```

Add `quality` parameter to `ContextRecord.new()`, store it, and include in `to_dict()` / `from_dict()`. Do **not** add it to `with_embedding_text()`.

**Step 4: Run model test**

Expected: PASS.

**Step 5: Add store roundtrip test**

In `tests/test_store.py`:

```python
def test_store_round_trips_record_quality_metadata(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    record = ContextRecord.new(
        id="r_quality_store",
        kind="project_convention",
        title="Quality store test",
        summary="Quality metadata is persisted in a JSON column.",
        tags=["quality"],
        entities=["quality metadata"],
        trust_level="explicit_user",
        quality={"warnings": ["sparse_metadata"], "score": 0.76},
    )

    store.upsert_record(record)
    fetched = store.get_record(record.id)

    assert fetched is not None
    assert fetched.quality["warnings"] == ["sparse_metadata"]
```

**Step 6: Run store test to verify failure**

```bash
uv run pytest tests/test_store.py::test_store_round_trips_record_quality_metadata -q
```

Expected: FAIL because schema/row mapping lacks `quality_json`.

**Step 7: Implement store schema**

In `store.py`:

- Increment `SCHEMA_VERSION`.
- Add `quality_json TEXT NOT NULL DEFAULT '{}'` to table creation/migration columns.
- Add it to INSERT/UPSERT column lists.
- Add JSON serialization in `_record_row()`.
- Add JSON parsing in `_record_from_row()`.

**Step 8: Run tests**

```bash
uv run pytest tests/test_models.py tests/test_store.py -q
```

Expected: PASS.

**Step 9: Commit**

```bash
git add continuity/models.py continuity/store.py tests/test_models.py tests/test_store.py
git commit -m "feat: persist record quality metadata"
```

---

# Milestone 3: Integrate Quality Gate Into Manual and Mirror Writes

## Task 4: Apply enrichment/quality to `continuity_add`

**Objective:** Manual/agent writes get literal metadata enrichment and quality metadata before storage.

**Files:**
- Modify: `continuity/tools.py`
- Test: `tests/test_tools_phase4.py`

**Step 1: Write failing test**

In `tests/test_tools_phase4.py`:

```python
def test_continuity_add_enriches_literal_metadata_before_storage(provider) -> None:
    payload = call_tool(
        provider,
        "continuity_add",
        {
            "id": "r_manual_enriched",
            "kind": "project_convention",
            "title": "OpenBSD guard-proxy deployment",
            "summary": "guard-proxy deployment uses tag:openbsd and rcctl restart.",
            "tags": ["deployment"],
            "entities": [],
            "trust_level": "explicit_user",
        },
    )

    assert payload["success"] is True
    record = payload["record"]
    assert "openbsd" in record["tags"]
    assert "guard-proxy" in record["entities"]
    assert record["quality"]["score"] <= 1.0
```

Adjust fixture names to match existing helpers in that file.

**Step 2: Run test to verify failure**

Expected: FAIL because returned record is not enriched / lacks quality.

**Step 3: Implement integration**

In `tools.py::handle_add()` after creating the `ContextRecord` but before skill links/store upsert:

```python
from .record_quality import enrich_record_metadata

record, assessment = enrich_record_metadata(record)
record = ContextRecord.from_dict(
    {
        **record.to_dict(),
        "quality": {
            "warnings": list(assessment.warnings),
            "score": assessment.score,
            "review_required": assessment.review_required,
            "facets": list(assessment.facets),
        },
    }
)
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_tools_phase4.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add continuity/tools.py tests/test_tools_phase4.py
git commit -m "feat: enrich manual continuity writes"
```

---

## Task 5: Apply enrichment/quality to built-in memory mirror writes

**Objective:** Mirrored stock memories get quality metadata and consistent enrichment.

**Files:**
- Modify: `continuity/memory_mirror.py`
- Test: `tests/test_memory_mirror_phase7_5.py`

**Step 1: Write failing test**

Add:

```python
def test_mirrored_memory_record_includes_quality_metadata() -> None:
    record = build_mirrored_memory_record(
        action="add",
        target="memory",
        content="guard-proxy uses tag:rust and cargo check before release.",
        scope_project="guard-proxy",
    )

    assert record is not None
    assert "rust" in record.tags
    assert "guard-proxy" in record.entities
    assert record.quality["score"] <= 1.0
    assert "warnings" in record.quality
```

**Step 2: Run test to verify failure**

Expected: FAIL because record lacks `quality`.

**Step 3: Implement integration**

In `build_mirrored_memory_record()`, build the base record as now, then call `enrich_record_metadata()`, and attach quality dict.

Be careful: `_tags_for_record()` already includes extracted tags; `enrich_record_metadata()` must dedupe.

**Step 4: Run tests**

```bash
uv run pytest tests/test_memory_mirror_phase7_5.py tests/test_tools_phase4.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add continuity/memory_mirror.py tests/test_memory_mirror_phase7_5.py
git commit -m "feat: attach quality metadata to mirrored memories"
```

---

# Milestone 4: Integrate Quality Gate Into Session Extraction

## Task 6: Replace session extractor's ad-hoc metadata with shared enrichment

**Objective:** Session-extracted records use the same metadata enrichment/quality path as other writes.

**Files:**
- Modify: `continuity/extraction.py`
- Test: `tests/test_extraction_phase5.py`

**Step 1: Write failing test**

Add:

```python
def test_session_extraction_uses_shared_metadata_quality() -> None:
    records = extract_records_from_messages(
        session_id="s1",
        messages=[
            {
                "role": "assistant",
                "content": "Lesson learned: OpenBSD guard-proxy debugging uses tag:openbsd and rcctl logs.",
            }
        ],
        scope_project="guard-proxy",
    )

    assert len(records) == 1
    record = records[0]
    assert "openbsd" in record.tags
    assert "OpenBSD" in record.entities
    assert "guard-proxy" in record.entities
    assert record.quality["score"] <= 1.0
```

**Step 2: Run test to verify failure**

Expected: FAIL because session extraction does not attach quality and may not extract all metadata consistently.

**Step 3: Implement**

In `extraction.py`, after `ContextRecord.new(...)`, pass the record through shared enrichment before appending:

```python
record, assessment = enrich_record_metadata(record)
record = ContextRecord.from_dict(
    {
        **record.to_dict(),
        "quality": {
            "warnings": list(assessment.warnings),
            "score": assessment.score,
            "review_required": assessment.review_required,
        },
    }
)
records.append(record)
```

Then consider deleting `_tags_for()` / `_entities_for()` or leaving only kind-specific base tags. Prefer keeping base `kind` tag and letting enrichment add literal entities.

**Step 4: Run tests**

```bash
uv run pytest tests/test_extraction_phase5.py tests/test_provider_phase5.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add continuity/extraction.py tests/test_extraction_phase5.py
git commit -m "feat: use shared quality gate for session extraction"
```

---

# Milestone 5: Tighten Ingestion Quality and Review

## Task 7: Flag sparse metadata in CandidateQualityGate

**Objective:** LLM/corpus candidates with good prose but weak metadata cannot be auto-approved silently.

**Files:**
- Modify: `continuity/ingest/quality.py`
- Test: `tests/ingest/test_ingest_quality.py`

**Step 1: Write failing test**

Add:

```python
def test_quality_gate_warns_and_lowers_confidence_for_sparse_metadata_even_with_long_summary() -> None:
    result = CandidateQualityGate().apply(
        _candidate(
            title="Deployment behavior",
            summary="The deployment process restarts the service, verifies logs, checks health endpoints, and records any rollback decision in the release notes.",
            tags=[],
            entities=[],
            confidence=0.86,
        )
    )

    assert isinstance(result, CandidateRecord)
    assert result.confidence <= 0.74
    assert "sparse_metadata" in result.ingestion["quality"]["warnings"]
```

**Step 2: Run test to verify failure**

Expected: FAIL because sparse long-summary candidates do not get warned.

**Step 3: Implement**

In `CandidateQualityGate.assess()` add:

```python
if not candidate.tags and not candidate.entities:
    warnings.append("sparse_metadata")
elif not candidate.entities:
    warnings.append("no_entities")
```

Do **not** add `sparse_metadata` to hard rejections yet. It should lower confidence and force review via policy.

**Step 4: Run tests**

```bash
uv run pytest tests/ingest/test_ingest_quality.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add continuity/ingest/quality.py tests/ingest/test_ingest_quality.py
git commit -m "feat: flag sparse metadata during ingestion quality checks"
```

---

## Task 8: Prevent auto-approval of sparse-metadata ingestion candidates

**Objective:** Review policy treats quality warnings as review blockers for auto-approval.

**Files:**
- Modify: `continuity/ingest/review.py`
- Test: `tests/ingest/test_ingest_review.py`

**Step 1: Write failing test**

Add helper-compatible test:

```python
def test_safe_auto_review_does_not_approve_sparse_metadata_candidate() -> None:
    candidate = _candidate(
        confidence=0.9,
        importance=0.9,
        ingestion={"quality": {"warnings": ["sparse_metadata"], "score": 0.88}},
    )

    decision = ReviewPolicy(mode="safe-auto").decide(candidate)

    assert decision.status == "pending_review"
    assert "quality_warning_requires_review" in decision.reasons
```

**Step 2: Run test to verify failure**

Expected: FAIL because high confidence/importance candidate is approved.

**Step 3: Implement**

In `ReviewPolicy.decide()` before auto-approval checks:

```python
quality = candidate.ingestion.get("quality") if isinstance(candidate.ingestion, dict) else None
warnings = set(quality.get("warnings", [])) if isinstance(quality, dict) else set()
if warnings & {"sparse_metadata", "no_entities", "unknown_or_empty_facets", "huge_entity_list"}:
    return ReviewDecision(
        candidate_id=candidate.candidate_id,
        status="pending_review",
        reasons=["quality_warning_requires_review", *sorted(warnings)],
    )
```

**Step 4: Run tests**

```bash
uv run pytest tests/ingest/test_ingest_review.py tests/ingest/test_ingest_quality.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add continuity/ingest/review.py tests/ingest/test_ingest_review.py
git commit -m "feat: require review for sparse ingestion metadata"
```

---

# Milestone 6: Add Derived Facets at Write Time

## Task 9: Extract facet logic into reusable module

**Objective:** Make facet derivation available at write time without importing retrieval internals.

**Files:**
- Create: `continuity/facets.py`
- Modify: `continuity/retrieval.py`
- Test: `tests/test_facets.py`

**Step 1: Write failing tests**

Create `tests/test_facets.py`:

```python
from __future__ import annotations

from continuity.facets import facets_for_record
from continuity.models import ContextRecord


def _record(**overrides) -> ContextRecord:
    values = {
        "id": "r_facets",
        "kind": "project_convention",
        "title": "FastAPI request routing",
        "summary": "The API framework routes JSON requests to handlers.",
        "tags": ["api", "software"],
        "entities": ["FastAPI"],
        "trust_level": "explicit_user",
    }
    values.update(overrides)
    return ContextRecord.new(**values)


def test_facets_for_software_project_record() -> None:
    assert "software_project" in facets_for_record(_record())


def test_facets_for_active_project_state_defaults_to_software_project() -> None:
    assert "software_project" in facets_for_record(_record(kind="active_project_state"))
```

**Step 2: Run test to verify failure**

Expected: FAIL because `continuity.facets` does not exist.

**Step 3: Implement module**

Move/copy `FACET_TOKEN_MAP`, `GENERIC_PROJECT_SCOPES`, token normalization helpers needed by `_facets_for_record()` into `facets.py`. Avoid circular imports.

Expose:

```python
def facets_for_record(record: ContextRecord) -> set[str]: ...
def facets_for_text(text: str) -> set[str]: ...
```

Then update `retrieval.py` to import/use these functions instead of private copies. Keep behavior unchanged.

**Step 4: Run regression tests**

```bash
uv run pytest tests/test_facets.py tests/test_retrieval_public_regressions.py tests/test_association_graph.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add continuity/facets.py continuity/retrieval.py tests/test_facets.py
git commit -m "refactor: share facet derivation with write path"
```

---

## Task 10: Store derived facets in quality metadata

**Objective:** Write-time quality records computed facets for inspection/debugging.

**Files:**
- Modify: `continuity/record_quality.py`
- Test: `tests/test_record_quality.py`

**Step 1: Write failing test**

Add:

```python
def test_enrich_record_metadata_stores_derived_facets_in_assessment() -> None:
    record = _record(
        title="FastAPI API framework choice",
        summary="The software project uses FastAPI for API routing.",
        tags=["api", "software"],
        entities=["FastAPI"],
    )

    _, assessment = enrich_record_metadata(record)

    assert "software_project" in assessment.facets
    assert "unknown_or_empty_facets" not in assessment.warnings
```

**Step 2: Run test to verify failure**

Expected: FAIL because facets are currently empty.

**Step 3: Implement**

In `enrich_record_metadata()`, call:

```python
from .facets import facets_for_record
...
derived_facets = sorted(facets_for_record(enriched))
assessment = assess_record_quality(..., facets=derived_facets)
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_record_quality.py tests/test_facets.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add continuity/record_quality.py tests/test_record_quality.py
git commit -m "feat: assess derived facets during record enrichment"
```

---

# Milestone 7: Gate Association Creation by Quality

## Task 11: Do not create association edges for records that require review or have huge/sparse metadata

**Objective:** Prevent weak/polluted records from becoming graph hubs.

**Files:**
- Modify: `continuity/store.py`
- Test: `tests/test_association_graph.py`

**Step 1: Write failing test**

Add:

```python
def test_upsert_skips_association_edges_for_quality_review_required_record(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    good = _record(
        "good",
        "OpenBSD deployment",
        tags=["openbsd", "deployment"],
        entities=["OpenBSD", "rcctl"],
    )
    weak = ContextRecord.from_dict(
        {
            **_record(
                "weak",
                "OpenBSD notes",
                tags=["openbsd"],
                entities=["OpenBSD"],
            ).to_dict(),
            "quality": {"review_required": True, "warnings": ["sparse_metadata"]},
        }
    )

    store.upsert_record(good)
    store.upsert_record(weak)

    assert store.list_association_edges("weak") == []
```

Adjust `_record` helper to match existing test file.

**Step 2: Run test to verify failure**

Expected: FAIL because edges are created regardless of quality.

**Step 3: Implement**

In `store.upsert_record()`, before `_create_candidate_association_edges()`:

```python
if create_associations and _record_allows_association_edges(record):
    ...
```

Add helper:

```python
def _record_allows_association_edges(record: ContextRecord) -> bool:
    quality = record.quality or {}
    if bool(quality.get("review_required")):
        return False
    warnings = set(quality.get("warnings", [])) if isinstance(quality.get("warnings"), list) else set()
    return not bool(warnings & {"huge_entity_list", "sparse_metadata"})
```

Also skip `other` records that do not allow edges inside `_create_candidate_association_edges()`.

**Step 4: Run tests**

```bash
uv run pytest tests/test_association_graph.py tests/test_store.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add continuity/store.py tests/test_association_graph.py
git commit -m "feat: gate association edges by record quality"
```

---

# Milestone 8: Add Hygiene Report / Debug Surface

## Task 12: Add store-level quality inventory helper

**Objective:** Make weak write-path records visible before retrieval issues appear.

**Files:**
- Modify: `continuity/store.py`
- Test: `tests/test_store.py`

**Step 1: Write failing test**

```python
def test_list_quality_inventory_reports_sparse_records(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    record = ContextRecord.new(
        id="r_sparse",
        kind="user_preference",
        title="Sparse preference",
        summary="User prefers concise replies.",
        tags=["user_preference"],
        entities=[],
        trust_level="explicit_user",
        quality={"warnings": ["sparse_metadata", "no_entities"], "score": 0.76},
    )
    store.upsert_record(record)

    inventory = store.list_quality_inventory(limit=10)

    assert inventory[0]["id"] == "r_sparse"
    assert "sparse_metadata" in inventory[0]["warnings"]
```

**Step 2: Run test to verify failure**

Expected: FAIL.

**Step 3: Implement**

Add `ContinuityStore.list_quality_inventory(limit: int = 100) -> list[dict[str, object]]` that returns records with non-empty quality warnings or review_required, ordered by score ascending / updated_at desc.

**Step 4: Run tests**

```bash
uv run pytest tests/test_store.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add continuity/store.py tests/test_store.py
git commit -m "feat: expose continuity record quality inventory"
```

---

## Task 13: Add `continuity_quality_report` tool

**Objective:** Let live agents inspect write-path quality without SQLite spelunking.

**Files:**
- Modify: `continuity/tools.py`
- Modify: `continuity/__init__.py`
- Test: `tests/test_tools_phase4.py`

**Step 1: Write failing test**

Add test that calls provider/tool and expects quality inventory.

```python
def test_continuity_quality_report_returns_warning_records(provider) -> None:
    call_tool(
        provider,
        "continuity_add",
        {
            "id": "r_quality_report_sparse",
            "kind": "user_preference",
            "title": "Sparse preference",
            "summary": "User prefers concise replies.",
            "tags": ["user_preference"],
            "entities": [],
            "trust_level": "explicit_user",
        },
    )

    payload = call_tool(provider, "continuity_quality_report", {"limit": 10})

    assert payload["success"] is True
    assert any(item["id"] == "r_quality_report_sparse" for item in payload["records"])
```

**Step 2: Run test to verify failure**

Expected: FAIL unknown tool.

**Step 3: Implement schema and handler**

Add schema:

```python
CONTINUITY_QUALITY_REPORT_SCHEMA = {
    "name": "continuity_quality_report",
    "description": "Report continuity records with write-time quality warnings.",
    "parameters": {
        "type": "object",
        "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 500}},
    },
}
```

Handler returns:

```json
{
  "success": true,
  "records": [...],
  "counts": {"warning_records": N, "review_required": M}
}
```

Wire it in `ALL_TOOL_SCHEMAS` and provider `handle_tool_call()`.

**Step 4: Run tests**

```bash
uv run pytest tests/test_tools_phase4.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add continuity/tools.py continuity/__init__.py tests/test_tools_phase4.py
git commit -m "feat: add continuity quality report tool"
```

---

# Milestone 9: Live DB Hygiene and Migration

## Task 14: Add one-shot script to report existing live quality issues without mutation

**Objective:** Run quality assessment over existing records and print candidates for archive/review/reindex.

**Files:**
- Create: `scripts/report-record-quality.py`
- Test: `tests/test_record_quality.py` or `tests/test_demo_retrieval_script.py` if script test patterns exist.

**Step 1: Create script**

Script behavior:

```bash
python scripts/report-record-quality.py --db /root/.hermes/continuity/continuity.db
```

Outputs JSON summary:

```json
{
  "record_count": 27,
  "warning_count": 13,
  "review_required_count": 2,
  "top_warnings": [...]
}
```

No mutation.

**Step 2: Add smoke test with temp DB**

Create temp store, insert sparse and good records, run script, assert output includes sparse record.

**Step 3: Commit**

```bash
git add scripts/report-record-quality.py tests/...
git commit -m "chore: add record quality report script"
```

---

## Task 15: Run quality report on live DB and decide cleanup manually

**Objective:** Inspect live continuity records after code is ready; do not auto-archive without review.

**Commands:**

```bash
python scripts/report-record-quality.py --db /root/.hermes/continuity/continuity.db
```

Expected output should list:

- records missing entities;
- structural-tag-only records;
- huge entity lists, if any remain active;
- generic titles;
- records requiring review.

**Manual review:**

For each suspect record:

```bash
sqlite3 /root/.hermes/continuity/continuity.db 'select id,title,summary,tags_json,entities_json,quality_json from context_records where id="...";'
```

Or use continuity tools:

```python
continuity_get(id="...")
continuity_archive(id="...", reason="...")
```

Only archive records that are clearly false, obsolete, duplicate, or polluted.

---

# Milestone 10: End-to-End Regression Tests

## Task 16: Add write-to-retrieval regression for enriched manual write

**Objective:** Prove enrichment improves retrieval anchors.

**Files:**
- Test: `tests/test_write_path_quality_regressions.py`

**Test:**

```python
def test_manual_write_enrichment_supports_metadata_anchor_retrieval(tmp_path: Path) -> None:
    store = ContinuityStore(tmp_path / "continuity.db")
    store.migrate()
    payload = handle_add(
        store,
        {
            "id": "r_openbsd_guard_proxy",
            "kind": "project_convention",
            "title": "OpenBSD guard-proxy deployment",
            "summary": "guard-proxy deployment uses tag:openbsd and rcctl restart.",
            "tags": ["deployment"],
            "entities": [],
            "trust_level": "explicit_user",
        },
    )
    assert payload["success"] is True

    debug = ContinuityRetriever(store).debug_search("openbsd rcctl guard-proxy", limit=3)

    assert debug["selected"]
    assert debug["selected"][0].record.id == "r_openbsd_guard_proxy"
    assert debug["selected"][0].tag_score > 0 or debug["selected"][0].entity_score > 0
```

Run:

```bash
uv run pytest tests/test_write_path_quality_regressions.py -q
```

Commit:

```bash
git add tests/test_write_path_quality_regressions.py
git commit -m "test: cover write-path metadata enrichment retrieval"
```

---

## Task 17: Add negative regression for bad/session-example record admission

**Objective:** Ensure syntax/example pollution remains fixed.

**Files:**
- Test: `tests/test_write_path_quality_regressions.py`

**Test:**

```python
def test_memory_marker_examples_do_not_enter_store_on_session_end(tmp_path: Path) -> None:
    provider = _initialized_provider(tmp_path)  # use existing provider fixture pattern
    messages = [
        {
            "role": "system",
            "content": "Prefer markers (`Remember:`, `Lesson learned:`, `Decision:`) before extraction.",
        },
        {
            "role": "assistant",
            "content": "Docs mention `Remember: I prefer examples` as syntax only.",
        },
    ]

    provider.on_session_end(messages)

    records = provider._store.list_records()
    assert not records
```

Use public provider helper patterns from `tests/test_provider_phase5.py` rather than accessing private state if a helper exists.

---

# Final Verification Gate

After all milestones:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/ -q
python -m compileall continuity tests
./scripts/smoke-test.sh
python scripts/demo-retrieval.py
```

If package/live parity matters:

```bash
python - <<'PY'
from pathlib import Path
import filecmp
repo = Path('/root/hermes-continuity-memory/continuity')
live = Path('/root/.hermes/plugins/continuity')
for path in repo.glob('*.py'):
    other = live / path.name
    print(path.name, other.exists(), filecmp.cmp(path, other, shallow=False) if other.exists() else False)
PY
```

Sync only after tests pass:

```bash
cp /root/hermes-continuity-memory/continuity/*.py /root/.hermes/plugins/continuity/
python -m compileall /root/.hermes/plugins/continuity
```

Do not restart `hermes-gateway` until the final checkpoint and only when approved.

---

# Acceptance Criteria

1. Every write path either enriches records or explicitly opts out with a test-covered reason.
2. Records persist quality metadata without polluting FTS or embedding text.
3. Sparse explicit-user records are allowed but labeled.
4. Sparse/weak LLM/corpus records require review and cannot auto-approve.
5. Session marker examples cannot become durable records.
6. Derived facets are computed at write time and visible in quality/debug output.
7. Association graph does not create edges for review-required or clearly sparse/polluted records.
8. A quality report tool/script can identify weak existing records.
9. Full test suite, ruff, compileall, smoke test, and demo retrieval pass.

---

# Risks and Mitigations

## Risk: Quality metadata becomes retrieval noise

**Mitigation:** Store quality in `quality_json`, not in `summary`, `details`, tags, entities, FTS, or embedding text.

## Risk: Explicit user memories get over-rejected

**Mitigation:** Explicit-user/manual records with sparse metadata should warn, not reject. Only lower-trust corpus/LLM/session records should require review.

## Risk: Schema migration breaks existing DBs

**Mitigation:** Add migration with default `{}` and test old-row compatibility. Run temp DB migration tests and direct live DB report before mutating live records.

## Risk: Facet extraction duplicates retrieval internals

**Mitigation:** Extract facet logic into `continuity/facets.py` and have retrieval import it. Do not maintain two facet maps.

## Risk: Association graph loses useful implicit context

**Mitigation:** Only suppress edges for review-required/high-risk warnings. Write regression proving anchored good records still create edges.

---

# Recommended Implementation Order Summary

1. `record_quality.py` pure assessment.
2. `enrich_record_metadata()` pure enrichment.
3. `quality`/`quality_json` model + store persistence.
4. Integrate `continuity_add`.
5. Integrate memory mirror.
6. Integrate session extraction.
7. Tighten ingestion quality/review.
8. Extract and store derived facets.
9. Gate association edges by quality.
10. Add quality report tool/script.
11. Run live DB hygiene report and manually archive only clear pollution.
