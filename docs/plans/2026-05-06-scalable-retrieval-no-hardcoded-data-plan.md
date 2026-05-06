# Scalable Retrieval Without Hardcoded Domain Data Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Replace hardcoded domain-specific retrieval behavior in the Continuity Memory plugin with flexible, corpus-derived, configurable, explainable retrieval that works for the general public without embedding private/user-specific facts in plugin code.

**Architecture:** Convert the retrieval system from global lexical policy (`if token == X, assume Y`) to a layered retrieval pipeline: lexical/vector candidate generation, corpus-derived entity/tag/facet evidence, optional dynamic query expansion from candidate metadata and graph neighborhoods, reranker validation, and conservative graph activation. Keep deterministic rules only for generic mechanics, safety, schema validation, and explainability; move domain knowledge into records, config, eval fixtures, or optional extraction/planning components.

**Tech Stack:** Python stdlib, SQLite/FTS5, existing `sentence-transformers` vector/reranker backends, pytest, ruff, compileall. No required hosted services. Optional LLM/NER/query-planner components must be explicitly configured and disabled by default.

---

## Background and Problem Statement

The current live plugin contains several non-scalable hardcoded retrieval rules:

- `retrieval.py::ALIASES` contains domain aliases like `boat -> sailboat/catamaran` and `tow -> raptor/truck`.
- `retrieval.py::FACET_TOKEN_MAP` contains fixed global domain facets such as `vehicle_towing`, `boating`, `personal_hardware`, `devops_security`, and tokens like `raptor`, `hobie`, `catalina`, `guard-proxy`, `spki`.
- `retrieval.py::INCOMPATIBLE_FACET_PAIRS` hardcodes global incompatibilities that can be false in legitimate contexts.
- `memory_mirror.py` extracts tags/entities using private/project-specific strings like `Ford Raptor`, `Framework Desktop`, `Ryzen AI Max 395`, and `guard-proxy`.
- `store.py::GENERIC_ASSOCIATION_TOKENS` uses a static boilerplate/generic-token list instead of corpus statistics.
- Association edge scoring uses fixed Jaccard weights and calls token overlap `semantic_similarity`.
- Retrieval scoring weights are global constants rather than config/eval-calibrated parameters.

These were useful to fix early regressions, but they bake one user's memories and projects into general plugin code. For public release, retrieval must become data-driven and inspectable.

## Non-Goals

- Do not require hosted LLM calls.
- Do not remove safety gates or lifecycle/staleness controls.
- Do not remove the association graph; make it more principled.
- Do not make memory injection more aggressive by default.
- Do not import private user-specific examples into public fixtures.
- Do not attempt a fully learned ranker in the first pass; build the deterministic/eval scaffolding first.

## Target Design

### New retrieval layers

1. **Normalization layer**
   - Lowercase, tokenize, singularize cautiously, normalize separators.
   - Keep only generic language-level normalization in code.
   - No domain aliases in code.

2. **Initial candidate generation**
   - FTS over record title/summary/details/tags/entities.
   - Vector search over `embedding_text`.
   - Exact metadata lookup over tags/entities/known aliases stored in the DB.
   - Optional source/scope filters.

3. **Corpus-derived vocabulary and statistics**
   - Build token/entity/tag statistics from records.
   - Compute document frequency / IDF-like weights.
   - Detect generic tokens from corpus statistics and structured fields, not static strings.

4. **Dynamic query expansion**
   - First pass retrieves candidates.
   - Expansion terms are proposed from high-confidence candidate tags/entities and graph-neighbor metadata.
   - Expansion terms must be explainable and bounded.
   - Expansion is second-pass candidate generation, not automatic injection.

5. **Facet evidence, not global facet dictionary**
   - Records may have explicit facets in metadata or derived fields.
   - Query facets are inferred from candidate evidence distribution and optional configured facet definitions.
   - Hardcoded public code can define only generic system facets like `memory_system` if absolutely necessary; domain facets belong in records/config.

6. **Compatibility gating**
   - Replace absolute hardcoded incompatible pairs with evidence-based compatibility:
     - shared explicit facet,
     - same scope/source/session,
     - strong entity/tag overlap,
     - strong reranker support,
     - strong graph path from anchored seed.
   - Config may define optional incompatible pairs, but public defaults should be minimal.

7. **Association graph edge creation**
   - Use IDF-weighted overlap for tags/entities/text.
   - Treat field types differently: entities > tags > body tokens.
   - Exclude boilerplate structurally by field/source, not by private strings.
   - Optionally incorporate vector similarity where available.
   - Keep edge creation threshold and out-degree cap configurable.

8. **Reranker validation and conservative injection**
   - Keep the reranker as a precision filter for direct candidates.
   - Allow graph rescue only from anchored candidates with strong evidence.
   - Dynamic expansion should increase candidate recall, not bypass validation.

9. **Debug-first implementation**
   - Every dynamic expansion term and graph edge must be explainable in `continuity_debug_retrieval`.
   - Public users should be able to answer: why was this memory selected?

---

## Acceptance Criteria

1. Public plugin code contains no private/user-specific domain strings such as `Raptor`, `Framework Desktop`, `Ryzen AI Max 395`, `Hobie`, `Catalina`, `Spruce Run`, `guard-proxy`, `SPKI`, or `Nemotron` outside tests that are explicitly private/local and excluded from public fixtures.
2. Domain-specific query aliases are removed from public retrieval code.
3. Built-in memory mirroring no longer injects domain tags/entities via hardcoded string checks.
4. Retrieval still handles the original boat/towing regression when equivalent facts are stored as records with tags/entities, but the mechanism is data-derived rather than code-derived.
5. Low-information queries such as `how about now` and `can you test and see if it's better now` still select no context unless current conversation context or explicit anchors justify retrieval.
6. Ambiguous terms such as `framework` do not retrieve unrelated hardware memories for software-framework queries in the synthetic public eval corpus.
7. `continuity_debug_retrieval` shows dynamic expansion terms, source candidate IDs, graph edge reasons, IDF/generic-token decisions, and cut reasons.
8. All current tests pass, plus new retrieval-quality tests for dynamic expansion, generic-token detection, association edge creation, and public demo corpus behavior.
9. Full quality gate passes: `uv run ruff format --check .`, `uv run ruff check .`, `uv run pytest tests/ -q`, `python -m compileall continuity tests`, demo retrieval script, smoke test.

---

## Implementation Strategy

Implement in small, reviewable phases. Each phase should start with failing tests and end with a clean commit.

### Phase 0: Inventory and regression freeze

Purpose: document current hardcoded behavior and freeze important regressions before changing retrieval.

#### Task 0.1: Add hardcoded-domain inventory test

**Objective:** Create a test that enumerates forbidden private/domain literals in public plugin files so future patches cannot reintroduce them.

**Files:**
- Create: `tests/test_public_no_private_domain_literals.py`

**Test design:**
- Scan `continuity/*.py` and public docs/scripts.
- Exclude test fixtures explicitly if needed, but prefer synthetic public examples.
- Forbidden literals initially:
  - `raptor`, `ford raptor`
  - `framework desktop`, `ryzen ai max`
  - `hobie`, `catalina`, `spruce run`, `round valley`
  - `guard-proxy`, `spki`, `reqwest`, `rustls` if they appear in generic retrieval heuristics rather than project-specific test data

**Verification:**
- Run: `uv run pytest tests/test_public_no_private_domain_literals.py -q`
- Expected initially: FAIL, proving the inventory catches current hardcoded data.

#### Task 0.2: Add synthetic retrieval regression corpus

**Objective:** Create public-safe records that exercise the same failure classes without private examples.

**Files:**
- Create: `tests/fixtures/retrieval_public/records.jsonl`
- Create: `tests/fixtures/retrieval_public/queries.jsonl`
- Create: `tests/test_retrieval_public_regressions.py`

**Synthetic domains:**
- Vehicle/towing analogue: `Blue Ridge Utility Van` + `folding camper` + `kayak trailer`.
- Ambiguous hardware/software analogue: `Atlas Workstation` vs `web application framework`.
- Memory-system meta queries: `association graph`, `retrieval`, `memory provider`.
- Low-info queries: `how about now`, `is it better?`.

**Acceptance:**
- Towing query retrieves vehicle and trailer/camper records without hardcoded aliases.
- Software-framework query does not retrieve workstation record.
- Meta-memory query retrieves memory-system records.
- Low-info query retrieves nothing.

#### Task 0.3: Add live/private regression notes outside public tests

**Objective:** Preserve the original boat/Raptor case as local/private evaluation documentation without shipping private data as public test fixture.

**Files:**
- Create: `docs/plans/private-regression-notes.md` or keep in local-only ignored path if repo will be public.
- Modify: `.gitignore` if using local-only private eval files.

**Acceptance:**
- Public repo can be published without exposing private facts.
- Developer still has a recipe for validating private live behavior separately.

---

### Phase 1: Separate retrieval constants into configuration

Purpose: make scoring and graph thresholds configurable before changing behavior.

#### Task 1.1: Add retrieval scoring config model

**Objective:** Move hardcoded scoring weights from `retrieval.py` constants into config with current values as defaults.

**Files:**
- Modify: `continuity/config.py`
- Modify: `continuity/retrieval.py`
- Test: `tests/test_config.py`
- Test: `tests/test_retrieval.py`

**Config fields:**

```python
@dataclass(frozen=True)
class RetrievalScoringConfig:
    scope_bonus: float = 1.0
    capsule_scope_bonus: float = 2.0
    tag_bonus: float = 1.5
    entity_bonus: float = 1.75
    text_match_bonus: float = 0.35
    confidence_weight: float = 0.5
    importance_weight: float = 0.5
    fts_weight: float = 1.0
    vector_weight: float = 3.0
    min_base_relevance: float = 0.35
    min_vector_relevance: float = 0.05
    min_vector_only_relevance: float = 2.75
```

**Acceptance:**
- Defaults produce unchanged existing test behavior.
- Config override changes scoring in a focused test.

#### Task 1.2: Add retrieval behavior config toggles

**Objective:** Add toggles for legacy aliases/facets during migration.

**Fields:**

```python
legacy_domain_aliases_enabled: bool = False
static_domain_facets_enabled: bool = False
corpus_dynamic_expansion_enabled: bool = True
idf_association_edges_enabled: bool = True
```

**Important:** Defaults for public release should be non-hardcoded behavior. If compatibility is needed during migration, enable legacy only in selected tests.

---

### Phase 2: Replace hardcoded query aliases with corpus-derived expansion

Purpose: remove domain-specific lexical expansion while retaining recall.

#### Task 2.1: Create vocabulary/statistics module

**Objective:** Build reusable corpus statistics from active records.

**Files:**
- Create: `continuity/vocabulary.py`
- Test: `tests/test_vocabulary.py`

**Core types:**

```python
@dataclass(frozen=True)
class CorpusTermStats:
    document_count: int
    term_document_frequency: dict[str, int]
    tag_document_frequency: dict[str, int]
    entity_document_frequency: dict[str, int]

    def idf(self, term: str) -> float: ...
    def is_generic(self, term: str, *, max_document_fraction: float = 0.35) -> bool: ...
```

**Token sources:**
- Title/summary/details tokens.
- Tags.
- Entities.
- Scope/project tokens optionally separate.

**Acceptance:**
- Common corpus tokens get lower IDF.
- Rare entities get higher IDF.
- Boilerplate record titles do not dominate if marked as boilerplate/source fields.

#### Task 2.2: Add dynamic expansion proposal API

**Objective:** Propose expansion terms from initial candidates rather than global aliases.

**Files:**
- Create: `continuity/dynamic_expansion.py`
- Test: `tests/test_dynamic_expansion.py`

**API:**

```python
@dataclass(frozen=True)
class ExpansionTerm:
    term: str
    source: str  # tag | entity | graph_neighbor_tag | graph_neighbor_entity
    source_record_ids: tuple[str, ...]
    score: float
    reason: str


def propose_expansion_terms(
    query_tokens: set[str],
    candidates: list[CandidateScore],
    store: ContinuityStore,
    stats: CorpusTermStats,
    *,
    max_terms: int = 8,
) -> list[ExpansionTerm]:
    ...
```

**Rules:**
- Only use candidates with at least one exact/FTS/tag/entity/text/vector evidence above threshold.
- Prefer tags/entities over body text.
- Ignore generic terms by IDF/document frequency.
- Bound max expansion terms.
- Return explanations.

**Acceptance:**
- Synthetic towing query proposes `trailer`, `camper`, `tow vehicle` from candidate metadata without hardcoded aliases.
- Low-info query proposes no terms.
- Unrelated vector-only candidate does not contribute expansion terms.

#### Task 2.3: Integrate second-pass retrieval

**Objective:** Run dynamic expansion after initial retrieval and before reranking/graph rescue.

**Files:**
- Modify: `continuity/retrieval.py`
- Test: `tests/test_retrieval_public_regressions.py`
- Test: `tests/test_retrieval.py`

**Flow:**

```text
query -> tokens -> initial FTS/vector/metadata candidates
      -> propose dynamic terms from anchored candidates
      -> second-pass FTS/metadata candidates with dynamic terms
      -> score/gates/reranker/graph
```

**Debug output additions:**

```json
"dynamic_expansion": [
  {
    "term": "camper",
    "source": "tag",
    "source_record_ids": ["..."],
    "score": 0.82,
    "reason": "high_idf_tag_from_anchored_candidate"
  }
]
```

**Acceptance:**
- `continuity_debug_retrieval` includes dynamic expansion terms.
- Existing retrieval tests pass.
- Public towing analogue passes without legacy aliases.

#### Task 2.4: Remove domain-specific entries from `ALIASES`

**Objective:** Keep only generic normalization aliases, or remove `ALIASES` entirely if dynamic expansion covers needed behavior.

**Files:**
- Modify: `continuity/retrieval.py`
- Test: `tests/test_public_no_private_domain_literals.py`

**Allowed examples:**
- `guard_proxy -> guard-proxy` is normalization and should probably live in `_normalize_token`, not `ALIASES`.
- `timeouts -> timeout` is generic language normalization.

**Forbidden examples:**
- `boat`, `tow`, `raptor`, `framework`, `guard-proxy` as domain expansion.

---

### Phase 3: Replace hardcoded memory mirroring tags/entities

Purpose: built-in memory mirrors should not know private/project entities.

#### Task 3.1: Introduce generic metadata extraction API

**Objective:** Extract candidate tags/entities from memory content using generic heuristics and known corpus vocabulary.

**Files:**
- Create: `continuity/metadata_extraction.py`
- Test: `tests/test_metadata_extraction.py`

**API:**

```python
@dataclass(frozen=True)
class ExtractedMetadata:
    tags: tuple[str, ...]
    entities: tuple[str, ...]
    facets: tuple[str, ...] = ()
    extraction_notes: tuple[str, ...] = ()


def extract_metadata(
    text: str,
    *,
    known_entities: set[str] | None = None,
    known_tags: set[str] | None = None,
) -> ExtractedMetadata:
    ...
```

**Generic heuristics:**
- Preserve explicit hashtags or `tag:`-style markers if present.
- Extract quoted proper-noun phrases and capitalized multi-word phrases.
- Match known entities/tags from existing records.
- Normalize code/project tokens that are explicit in text, but do not map them to extra domain tags.
- Do not infer `boat` from `Raptor` or `local_llm` from `Ryzen`.

**Acceptance:**
- `Blue Ridge Utility Van` is extracted as entity because it is a capitalized phrase.
- `Ford Raptor` would be extracted generically if present, but no special tags are added.
- `guard-proxy` can be extracted as an entity/project token if literally present, without hardcoded project_status tags.

#### Task 3.2: Rewrite `memory_mirror.py` to use generic extraction

**Objective:** Remove private string checks from `_tags_for_record` and `_entities_for_record`.

**Files:**
- Modify: `continuity/memory_mirror.py`
- Test: `tests/test_memory_mirror_phase7_5.py`
- Test: `tests/test_public_no_private_domain_literals.py`

**Behavior:**
- Always include structural tags: `built_in_memory`, `memory_target:user|memory`, record kind.
- Add extracted tags/entities from generic extractor only.
- Preserve safety/redaction/truncation.

**Acceptance:**
- Mirror records remain searchable via literal content and extracted entities.
- No private domain strings remain in `memory_mirror.py`.

#### Task 3.3: Improve memory write API guidance

**Objective:** Encourage agent/user-provided metadata where available instead of inferred private rules.

**Files:**
- Modify: `docs/CONFIGURATION.md`
- Modify: `README.md`
- Maybe modify Hermes integration docs if present.

**Documentation:**
- Explain that explicit continuity records with tags/entities/facets are highest quality.
- Built-in memory mirrors are conservative and do not infer broad domain tags.

---

### Phase 4: Replace hardcoded facet maps with record-derived facets

Purpose: avoid global ontology whack-a-mole.

#### Task 4.1: Add optional facets field to ContextRecord

**Objective:** Support explicit record facets without encoding them in tags.

**Files:**
- Modify: `continuity/models.py`
- Modify: `continuity/store.py` schema migration
- Test: `tests/test_models.py`
- Test: `tests/test_store.py`

**Design:**
- Add `facets: list[str] = field(default_factory=list)` to `ContextRecord`.
- Store as `facets_json` column.
- Include facets in `embedding_text` and debug output.
- Keep facets optional; old DB rows default to empty list.

**Acceptance:**
- Existing records load with `facets=[]`.
- New records can store/load facets.

#### Task 4.2: Implement query facet evidence from candidates

**Objective:** Infer query facets from candidate evidence, not static token lists.

**Files:**
- Create: `continuity/facets.py`
- Test: `tests/test_facets.py`

**API:**

```python
@dataclass(frozen=True)
class FacetEvidence:
    facet: str
    score: float
    source_record_ids: tuple[str, ...]
    reason: str


def infer_query_facets(
    query_tokens: set[str],
    candidates: list[CandidateScore],
    *,
    min_score: float = 0.5,
) -> list[FacetEvidence]:
    ...
```

**Evidence sources:**
- Candidate explicit facets.
- Candidate tags/entities matching query tokens.
- Strong reranker candidates.
- Scope/source context.

**Acceptance:**
- Query facets are empty for low-info queries.
- Query facets emerge for anchored synthetic corpus queries.

#### Task 4.3: Replace hardcoded incompatible pairs with compatibility scoring

**Objective:** Use a compatibility function rather than absolute static incompatible pairs.

**Files:**
- Modify: `continuity/facets.py`
- Modify: `continuity/retrieval.py`
- Test: `tests/test_facets.py`
- Test: `tests/test_retrieval_quality_eval.py`

**API:**

```python
def candidate_compatible(
    query_facet_evidence: list[FacetEvidence],
    candidate: CandidateScore,
    *,
    strict: bool,
) -> tuple[bool, str]:
    ...
```

**Rules:**
- Compatible if no facet evidence exists.
- Compatible if candidate shares strong facet/source/entity/tag evidence.
- If candidate has unrelated facets, reject only when query has strong evidence for a different facet and candidate lacks any anchor.
- Allow config-defined incompatible pairs as optional user/project config, not public default code.

**Acceptance:**
- Synthetic software-framework query rejects workstation hardware record because it lacks shared evidence.
- A query about running software on a workstation can retrieve both software and hardware if records share explicit source/entity/facet anchors.

---

### Phase 5: Make association graph edge creation corpus-aware

Purpose: improve graph quality without static generic tokens.

#### Task 5.1: Refactor association strength into its own module

**Objective:** Move graph scoring from `store.py` to `association.py` and make it testable.

**Files:**
- Create: `continuity/association.py`
- Modify: `continuity/store.py`
- Test: `tests/test_association_graph.py`

**API:**

```python
@dataclass(frozen=True)
class AssociationEvidence:
    strength: float
    edge_type: str
    shared_entities: tuple[str, ...]
    shared_tags: tuple[str, ...]
    shared_terms: tuple[str, ...]
    reasons: tuple[str, ...]


def association_evidence(
    left: ContextRecord,
    right: ContextRecord,
    stats: CorpusTermStats | None = None,
) -> AssociationEvidence:
    ...
```

**Acceptance:**
- Existing edge creation can call new function.
- Debug inventory can later expose evidence.

#### Task 5.2: Add IDF-weighted overlap

**Objective:** Replace fixed generic token filtering with corpus-weighted overlap.

**Formula sketch:**

```text
entity_score = weighted_jaccard(shared_entities, all_entities, idf)
tag_score = weighted_jaccard(shared_tags, all_tags, idf)
text_score = weighted_jaccard(shared_text_terms, all_text_terms, idf)
strength = bounded(entity_weight * entity_score + tag_weight * tag_score + text_weight * text_score + exact_entity_bonus)
```

**Important:**
- Use separate weights for fields.
- Ignore structural fields like record kind/title boilerplate unless explicitly configured.
- Rare shared entities should matter more than common shared tags.

**Acceptance:**
- Records sharing only boilerplate/user/memory terms do not form edges.
- Records sharing a rare entity form a strong edge.
- Records sharing common tags only form weak/no edge.

#### Task 5.3: Add association evidence to debug tools

**Objective:** Make edge relatedness inspectable.

**Files:**
- Modify: `continuity/tools.py`
- Modify: `continuity/store.py`
- Test: `tests/test_tools_phase4.py`

**Output addition:**

```json
{
  "strength": 0.72,
  "edge_type": "entity_overlap",
  "shared_entities": ["Blue Ridge Utility Van"],
  "shared_tags": ["trailer"],
  "reasons": ["rare_shared_entity", "tag_overlap"]
}
```

---

### Phase 6: Dynamic graph-aware retrieval without noisy fanout

Purpose: keep graph rescue valuable but make it general.

#### Task 6.1: Use dynamic expansion terms as graph anchors

**Objective:** Allow graph traversal only when seeds are anchored by query terms, expansion evidence, or candidate metadata.

**Files:**
- Modify: `continuity/retrieval.py`
- Test: `tests/test_association_graph.py`

**Rules:**
- A rejected below-reranker candidate can seed graph if:
  - it has direct FTS/tag/entity/text anchor, or
  - it was reached through a high-confidence dynamic expansion term with source evidence.
- Weak vector-only candidates cannot seed graph.
- Low-info queries cannot seed graph unless conversation context supplies an explicit anchor in future work.

#### Task 6.2: Add graph-neighbor expansion with strict bounds

**Objective:** Let graph neighbors propose expansion terms before final selection, but not bypass gates.

**Files:**
- Modify: `continuity/dynamic_expansion.py`
- Test: `tests/test_dynamic_expansion.py`

**Rules:**
- Only one-hop neighbors from strong anchored candidates.
- Only use high-IDF tags/entities from neighbors.
- Limit total graph-derived expansion terms.
- Record `source_record_ids` and edge IDs/reasons.

**Acceptance:**
- Synthetic implicit-context query retrieves related neighbor record via graph-derived expansion.
- Bad/noisy edge does not inject context if reranker/facet/evidence fails.

---

### Phase 7: Optional query planner interface

Purpose: provide a future path for flexible query understanding without requiring it.

#### Task 7.1: Define query planner protocol

**Objective:** Add an optional interface for local/explicitly configured query planning.

**Files:**
- Create: `continuity/query_planner.py`
- Test: `tests/test_query_planner.py`

**API:**

```python
@dataclass(frozen=True)
class QueryPlan:
    intent: str | None = None
    desired_context: tuple[str, ...] = ()
    candidate_terms: tuple[str, ...] = ()
    negative_terms: tuple[str, ...] = ()
    facets: tuple[str, ...] = ()
    confidence: float = 0.0
    notes: tuple[str, ...] = ()

class QueryPlanner(Protocol):
    def plan(self, query: str) -> QueryPlan: ...
```

**Default implementation:**
- `NoopQueryPlanner` returns empty low-confidence plan.

**Acceptance:**
- Retrieval works identically with noop planner.
- Fake test planner can add candidate terms and debug shows planner source.

#### Task 7.2: Add privacy/config docs for planner

**Objective:** Make clear that LLM-based planners are optional and local/private by default.

**Docs:**
- Planner can be local-only.
- Remote planners require explicit configuration.
- Planner output is hints only; never treated as truth.

---

### Phase 8: Remove legacy hardcoded data and update public docs

Purpose: make repo public-safe and explain the new retrieval model.

#### Task 8.1: Delete legacy static domain maps

**Objective:** Remove or disable `ALIASES`, `FACET_TOKEN_MAP`, `INCOMPATIBLE_FACET_PAIRS`, and private memory mirror rules.

**Files:**
- Modify: `continuity/retrieval.py`
- Modify: `continuity/memory_mirror.py`
- Test: `tests/test_public_no_private_domain_literals.py`

**Acceptance:**
- Forbidden-literal scan passes.
- Public regression tests pass.

#### Task 8.2: Update README retrieval section

**Objective:** Describe scalable retrieval accurately.

**Files:**
- Modify: `README.md`
- Modify: `docs/CONFIGURATION.md`
- Modify: `docs/TROUBLESHOOTING.md`

**Key wording:**
- Continuity does not ship with your private ontology.
- It derives retrieval hints from records, metadata, graph edges, vectors, and reranking.
- Explicit tags/entities/facets improve recall.
- Debug tools show why context was or was not selected.

#### Task 8.3: Update demo retrieval corpus

**Objective:** Demonstrate dynamic expansion publicly.

**Files:**
- Modify: `examples/demo_memory/records.jsonl`
- Modify: `examples/demo_memory/queries.jsonl`
- Modify: `scripts/demo-retrieval.py`

**Acceptance:**
- Demo contains no private/user-specific examples.
- Demo exercises:
  - dynamic expansion,
  - graph rescue,
  - low-info no-context,
  - ambiguous-term disambiguation,
  - stale/archive exclusion.

---

### Phase 9: Evaluation and calibration

Purpose: prevent regressions and tune thresholds using public-safe evals.

#### Task 9.1: Add retrieval eval runner enhancements

**Objective:** Evaluate precision, not only recall.

**Files:**
- Modify existing eval runner if present, or create: `scripts/retrieval-eval.py`
- Test: `tests/test_retrieval_eval_runner.py`

**Eval fields:**

```json
{
  "query": "what can tow the folding camper?",
  "expected_titles_top_k": {"k": 3, "titles": ["Blue Ridge Utility Van"]},
  "forbidden_titles": ["Atlas Workstation"],
  "expect_no_context": false
}
```

**Metrics:**
- Top-1 hit.
- Top-3 recall.
- Forbidden hit count.
- No-context accuracy.
- Average selected count.

#### Task 9.2: Calibrate default thresholds

**Objective:** Use eval output to tune config defaults.

**Commands:**
- `uv run pytest tests/test_retrieval_public_regressions.py -q`
- `python scripts/demo-retrieval.py`
- `python scripts/retrieval-eval.py examples/demo_memory/queries.jsonl`

**Acceptance:**
- Defaults are conservative: prefer no context over noisy context.
- Dynamic expansion improves recall in expected cases.
- Forbidden/noise cases remain clean.

---

### Phase 10: Live/repo sync and final verification

Purpose: keep live plugin and repo aligned without losing Discord session.

#### Task 10.1: Verify active plugin path

**Objective:** Confirm whether live gateway loads from `~/.hermes/plugins/continuity/` or repo package.

**Commands:**
- Use `continuity_status` to inspect DB/provider status.
- Use a direct Python import with `PYTHONPATH=/root/.hermes/plugins` to inspect live plugin path.

**Acceptance:**
- Active path is documented in handoff notes.

#### Task 10.2: Run full quality gate in repo

**Commands:**

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/ -q
python -m compileall continuity tests
./scripts/smoke-test.sh
python scripts/demo-retrieval.py
uv build
```

**Acceptance:** all pass.

#### Task 10.3: Secret/private-data scan before public release

**Commands:**

```bash
gitleaks detect --source . --no-git --verbose
gitleaks detect --source . --verbose
```

**Acceptance:** no private facts/secrets in working tree or history. If history contains private data and repo has not been published, rewrite local history before release.

---

## Suggested Milestone Commits

1. `test: add public-safe retrieval hardcoding inventory`
2. `test: add synthetic retrieval regression corpus`
3. `config: make retrieval scoring configurable`
4. `feat: add corpus vocabulary statistics`
5. `feat: add dynamic query expansion from candidate metadata`
6. `refactor: remove domain-specific query aliases`
7. `feat: add generic metadata extraction for memory mirrors`
8. `refactor: remove domain-specific mirror tagging`
9. `feat: add explicit record facets`
10. `feat: infer query facets from candidate evidence`
11. `refactor: move association scoring into association module`
12. `feat: use IDF-weighted association evidence`
13. `feat: add graph-derived expansion with strict gates`
14. `feat: add optional query planner interface`
15. `docs: document scalable retrieval architecture`
16. `test: add public demo retrieval evals`
17. `chore: remove legacy hardcoded domain data`

---

## Risks and Mitigations

### Risk: Dynamic expansion increases noise

**Mitigation:**
- Expansion terms only come from anchored candidates.
- Expansion terms are bounded and IDF-filtered.
- Expansion produces candidates, not selected memories.
- Reranker/facet/graph gates remain conservative.

### Risk: Removing aliases hurts recall

**Mitigation:**
- Keep vector recall and metadata exact matching.
- Add second-pass dynamic expansion.
- Add public and private retrieval evals before removal.
- Use feature flags during migration.

### Risk: IDF statistics are unstable with small corpora

**Mitigation:**
- Smooth IDF values.
- Fall back to structural field weighting for small record counts.
- Avoid aggressive generic-token decisions until corpus has enough records.

### Risk: Explicit facets add schema complexity

**Mitigation:**
- Facets are optional.
- Existing records default to empty facets.
- Retrieval remains functional without facets.

### Risk: Optional query planner causes privacy issues

**Mitigation:**
- Disabled by default.
- Local/noop default implementation.
- Docs warn that remote planners require explicit consent/configuration.
- Planner output is hints only.

---

## Final Definition of Done

The work is complete when:

- Public code has no private/user-specific retrieval knowledge.
- Dynamic retrieval handles synthetic analogues of the boat/towing, hardware/software ambiguity, memory-meta, and low-information regressions.
- Memory mirroring is generic and conservative.
- Association graph edges are corpus-aware and explainable.
- Debug tools expose enough evidence to understand retrieval decisions.
- Docs describe the architecture honestly, including limitations.
- Full tests, smoke tests, demo retrieval, compileall, formatting, linting, build, and secret/private-data scans pass.
