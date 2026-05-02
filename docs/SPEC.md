# Hermes Continuity Memory Plugin Full Specification

> **For Hermes / future agents:** This is the canonical planning/spec document for building a standalone GitHub-distributable Hermes memory plugin that provides human-like continuity without bloating the active prompt. Use the `subagent-driven-development` skill to implement this spec task-by-task. Use strict TDD for every production behavior.

**Working name:** `hermes-continuity-memory`

**Goal:** Build a pluggable, local-first Hermes memory provider that stores rich long-term context externally, retrieves compact relevant summaries per turn, and lets Hermes reconstruct deeper details on demand without maintaining a fork of `hermes-agent`.

**Primary distribution target:** Standalone GitHub repository installable into `$HERMES_HOME/plugins/continuity/` and enabled via `memory.provider: continuity`.

**Architecture:** Implement a `MemoryProvider` plugin named `continuity`. Use SQLite + FTS5 as the required baseline. Store structured `ContextRecord`s with provenance/source references. Enforce strict retrieval budgets in `prefetch()`. Add optional vector/hybrid retrieval only after schema, evals, and FTS retrieval are stable.

**Non-goal:** Replace Hermes built-in `MEMORY.md` / `USER.md`, skills, or `session_search`. This plugin complements them.

---

## 1. Problem statement

Hermes has several useful memory/context systems today:

- `MEMORY.md` and `USER.md`: tiny curated Tier 0 memory, always injected at session start.
- Skills: explicit procedural memory, loaded on demand.
- Session search: on-demand archive search across previous conversations.
- Context compression: active-session summarization near context limits.
- External memory provider API: optional provider hooks for prefetch/sync/session-end.

What is missing is a local-first continuity layer that behaves more like human memory:

- It stores many experiences, summaries, lessons, decisions, and project facts.
- It does not keep all of them active in the prompt.
- It retrieves only a small relevant working set for the current turn.
- It can link compact summaries back to exact source details.
- It is inspectable, testable, and safe against stale or untrusted context.

---

## 2. Product principles

### 2.1 Store generously, inject conservatively

The plugin may store thousands/millions of records, but `prefetch()` must return a small bounded context block.

Default target:

```yaml
max_records: 5
max_chars: 1800
```

### 2.2 Recall small, verify deep

Normal retrieval should return compact records:

```text
Lesson: delegate_task can timeout with api_calls:0 after exactly 300s; repeated delegation may be wasteful.
Sources: session:abc turns 44-59
```

It should not inject raw transcript/log chunks unless explicitly requested by a tool or later expansion phase.

### 2.3 Summaries are recall handles; sources are verification

Every extracted memory should contain source refs where possible:

- session id
- approximate turn range
- file path
- git commit
- command/test artifact
- user-provided source label

### 2.4 Skills remain procedural memory

Repeated procedures should become Hermes skills. The continuity plugin may store `procedure_candidate` records and suggest skill creation, but it should not replace skills.

### 2.5 Built-in memory remains Tier 0

`MEMORY.md` / `USER.md` remain the small, high-confidence, always-injected layer. The continuity plugin may mirror/index those writes, but built-in memory is still the source of always-active facts.

### 2.6 Retrieved memory is data, not instruction

All automatic prefetch output must be framed as recalled informational context. It must not be treated as system/developer/user instruction. Hermes already wraps provider prefetch in `<memory-context>`; the plugin should not emit instruction-like text.

### 2.7 Repeatability requires evals

Before tuning retrieval, create fixture records and queries. Retrieval quality should be measured with deterministic tests.

---

## 3. Existing Hermes extension points to use

The plugin must use the existing `MemoryProvider` API:

```python
class MemoryProvider:
    name: str
    is_available() -> bool
    initialize(session_id: str, **kwargs) -> None
    system_prompt_block() -> str
    prefetch(query: str, *, session_id: str = "") -> str
    queue_prefetch(query: str, *, session_id: str = "") -> None
    sync_turn(user_content: str, assistant_content: str, *, session_id: str = "") -> None
    on_session_end(messages: list[dict]) -> None
    on_pre_compress(messages: list[dict]) -> str
    on_memory_write(action: str, target: str, content: str) -> None
    on_delegation(task: str, result: str, *, child_session_id: str = "", **kwargs) -> None
    get_tool_schemas() -> list[dict]
    handle_tool_call(tool_name: str, args: dict, **kwargs) -> str
    shutdown() -> None
```

Plugin install locations:

```text
$HERMES_HOME/plugins/continuity/
```

or bundled upstream later:

```text
plugins/memory/continuity/
```

Activation:

```yaml
memory:
  provider: continuity
```

---

## 4. Repository/package layout

Standalone repository target:

```text
hermes-continuity-memory/
├── README.md
├── LICENSE
├── pyproject.toml
├── plugin.yaml
├── continuity/
│   ├── __init__.py          # MemoryProvider + register(ctx)
│   ├── models.py            # dataclasses and validation
│   ├── store.py             # SQLite schema, migrations, CRUD, FTS
│   ├── retrieval.py         # FTS/scoring/hybrid retrieval
│   ├── extraction.py        # session/turn consolidation
│   ├── project.py           # project/repo identity detection
│   ├── tools.py             # tool schemas and handlers
│   ├── security.py          # prompt-injection/secret filtering
│   ├── config.py            # config loading/defaults
│   ├── embeddings.py        # optional phase 5 vector support
│   └── install.py           # optional local install helper
├── tests/
│   ├── fixtures/
│   │   └── continuity_memory/
│   │       ├── records.jsonl
│   │       ├── queries.jsonl
│   │       └── sessions.jsonl
│   ├── test_provider_discovery.py
│   ├── test_store.py
│   ├── test_retrieval.py
│   ├── test_tools.py
│   ├── test_extraction.py
│   ├── test_project.py
│   ├── test_security.py
│   └── test_eval_fixtures.py
└── scripts/
    ├── install.sh
    └── run-tests.sh
```

Installed Hermes plugin layout:

```text
$HERMES_HOME/plugins/continuity/
├── __init__.py
├── plugin.yaml
├── models.py
├── store.py
├── retrieval.py
├── extraction.py
├── project.py
├── tools.py
├── security.py
├── config.py
└── embeddings.py
```

---

## 5. Data model

### 5.1 `ContextRecord`

Required logical fields:

```python
@dataclass
class ContextRecord:
    id: str
    kind: str
    scope_user: str | None
    scope_project: str | None
    scope_repo: str | None
    scope_profile: str | None
    title: str
    summary: str
    details: str | None
    tags: list[str]
    entities: list[str]
    sources: list[SourceRef]
    confidence: float
    importance: float
    trust_level: str
    created_at: str
    updated_at: str
    last_accessed_at: str | None
    last_confirmed_at: str | None
    expires_at: str | None
    source_hash: str | None
    embedding_text: str | None
```

### 5.2 `SourceRef`

```python
@dataclass
class SourceRef:
    type: str          # session, file, git, tool, user, memory, delegation
    id: str | None
    uri: str | None
    range: str | None
    label: str | None
    created_at: str | None
```

Examples:

```json
{"type":"session","id":"2026-04-guard-proxy","range":"turns 44-59","label":"delegate timeout debugging"}
```

```json
{"type":"file","uri":"~/src/guard-proxy/src/proxy.rs","label":"timeout handling implementation"}
```

### 5.3 Record kinds

MVP kinds:

- `user_preference`
- `environment_fact`
- `project_convention`
- `lesson_learned`
- `decision`
- `session_summary`
- `artifact_summary`
- `procedure_candidate`
- `open_question`
- `active_project_state`

### 5.4 Trust levels

Initial trust levels:

- `explicit_user`
- `built_in_memory_mirror`
- `agent_observed`
- `session_extracted`
- `tool_observed`
- `remote_untrusted`

Default for extracted records: `session_extracted`.

Records from built-in `memory` writes: `built_in_memory_mirror`.

User-created via tool: `explicit_user`.

---

## 6. Storage schema

Baseline must be SQLite + FTS5.

### 6.1 Required SQLite tables

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS context_records (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  scope_user TEXT,
  scope_project TEXT,
  scope_repo TEXT,
  scope_profile TEXT,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  details TEXT,
  tags_json TEXT NOT NULL DEFAULT '[]',
  entities_json TEXT NOT NULL DEFAULT '[]',
  sources_json TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL DEFAULT 0.5,
  importance REAL NOT NULL DEFAULT 0.5,
  trust_level TEXT NOT NULL DEFAULT 'session_extracted',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_accessed_at TEXT,
  last_confirmed_at TEXT,
  expires_at TEXT,
  source_hash TEXT,
  embedding_text TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS context_records_fts USING fts5(
  id UNINDEXED,
  title,
  summary,
  details,
  tags,
  entities
);

CREATE TABLE IF NOT EXISTS session_observations (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  turn_index INTEGER,
  user_content TEXT,
  assistant_content TEXT,
  created_at TEXT NOT NULL,
  consolidated INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS retrieval_events (
  id TEXT PRIMARY KEY,
  query TEXT NOT NULL,
  selected_ids_json TEXT NOT NULL,
  skipped_ids_json TEXT NOT NULL DEFAULT '[]',
  scores_json TEXT NOT NULL DEFAULT '{}',
  max_chars INTEGER,
  created_at TEXT NOT NULL
);
```

### 6.2 Storage path

Default:

```text
$HERMES_HOME/continuity/continuity.db
```

Config override:

```yaml
memory:
  continuity:
    db_path: /custom/path/continuity.db
```

### 6.3 Definition of done

- SQLite DB initializes idempotently.
- All migrations are tracked and re-runnable.
- CRUD round-trips all `ContextRecord` fields.
- FTS entries update on insert/update/delete.
- Tests use temporary `HERMES_HOME` or explicit temp DB path.

---

## 7. Configuration

Default config namespace:

```yaml
memory:
  provider: continuity
  continuity:
    db_path: null
    max_records: 5
    max_chars: 1800
    min_score: 0.1
    include_sources: true
    include_scores: false
    save_turn_observations: true
    consolidate_on_session_end: true
    consolidate_min_turns: 3
    session_strategy: per-repo     # per-repo | per-directory | global | per-session
    project_scope_boost: 1.0
    stale_after_days: 180
    vector:
      enabled: false
      backend: none                # none | sqlite-vec | lancedb
      embedding_model: null
```

Definition of done:

- Config loads with sane defaults if absent.
- Env/config failures degrade safely.
- Bad config values are clamped or ignored with debug warnings, not fatal crashes.

---

## 8. Retrieval behavior

### 8.1 MVP retrieval: FTS + metadata scoring

MVP must not require embeddings.

Candidate generation:

1. FTS query over title/summary/details/tags/entities.
2. Tag/entity exact-match scan.
3. Optional recent/high-importance fallback if no FTS hit and project scope matches.

Scoring formula v1:

```text
score =
    fts_score
  + exact_entity_bonus
  + tag_bonus
  + scope_bonus
  + importance_bonus
  + confidence_bonus
  + recency_bonus
  - stale_penalty
  - trust_penalty
```

Specific constants should be in `retrieval.py` and covered by tests.

### 8.2 Query context

`prefetch(query)` input is the current user message. The plugin should enrich internally with:

- current project id
- git repo remote if detectable
- active profile if passed to `initialize`
- session id
- platform/user id if passed

### 8.3 Output format

Automatic prefetch output should be compact and deterministic:

```text
Relevant continuity memory:
1. [lesson_learned | project=guard-proxy | confidence=0.92]
   delegate_task can return status:timeout with api_calls:0 after exactly 300s; repeated delegation may keep failing, so work inline.
   Sources: session:2026-04-... turns 44-59
```

No raw transcripts by default.

### 8.4 Budgeting

`prefetch()` must guarantee:

- at most `max_records`
- at most `max_chars`
- no partial malformed records
- gracefully return `""` when no records qualify

### 8.5 Definition of done

- Retrieval eval fixtures pass.
- Exact-term queries retrieve expected exact records.
- Fuzzy-ish lexical queries retrieve expected tagged/entity records when possible.
- Project scope boosts relevant records above global distractors.
- Low confidence/stale records are demoted.
- `prefetch()` never exceeds configured `max_chars`.

---

## 9. Tools exposed to Hermes

### 9.1 `continuity_status`

Returns provider status:

```json
{
  "success": true,
  "initialized": true,
  "db_path": "...",
  "record_count": 42,
  "session_id": "...",
  "current_project": "...",
  "max_records": 5,
  "max_chars": 1800,
  "vector_enabled": false
}
```

### 9.2 `continuity_search`

Inputs:

```json
{
  "query": "delegate timeout",
  "limit": 5,
  "scope_project": "guard-proxy"
}
```

Returns ranked records with scores and source refs.

### 9.3 `continuity_get`

Fetch one record by id, including full details and sources.

### 9.4 `continuity_add`

Add explicit record. Must validate kind, summary, trust level, and scan for unsafe content.

### 9.5 `continuity_delete`

Delete one record by id.

### 9.6 `continuity_expand`

Phase 2+. Given a record id, retrieve source details if available from local observations/session refs. In MVP this may return sources only with `not_implemented` for raw expansion.

### 9.7 Definition of done

- Every tool returns valid JSON string.
- Tool schemas validate under OpenAI function schema shape.
- Unknown tool names return JSON error.
- Tools are safe if provider is uninitialized.
- Tests cover success and error cases.

---

## 10. Session consolidation

### 10.1 Per-turn observations

`sync_turn(user_content, assistant_content)` should optionally persist a lightweight observation to `session_observations`.

Definition of done:

- Turns are stored crash-safely when `save_turn_observations` is true.
- Large messages are truncated or summarized according to config.
- Secrets are filtered before storage where feasible.

### 10.2 Session-end extraction

`on_session_end(messages)` should:

1. Skip if disabled or too few turns.
2. Build extraction input from session messages or stored observations.
3. Ask an LLM or deterministic extractor to produce candidate records.
4. Validate candidate JSON.
5. Scan for secrets/injection.
6. Dedupe/merge with existing records.
7. Store records with source refs.
8. Mark observations consolidated.

MVP may use a conservative heuristic extractor and explicit tools before introducing LLM extraction if standalone plugin access to an auxiliary LLM is inconvenient. If using LLM extraction, it must degrade gracefully when no provider is available.

### 10.3 Extraction prompt requirements

If using an LLM, extraction prompt must instruct:

- Extract durable facts only.
- Prefer concise summaries.
- Do not save temporary TODOs or raw logs.
- Preserve source refs.
- Output strict JSON.
- Do not store secrets.
- Use allowed `kind` values only.

### 10.4 Definition of done

- Meaningful session fixture produces expected records.
- Trivial session fixture produces no records.
- Duplicate lesson across sessions updates/merges instead of duplicating.
- Unsafe content is rejected.
- Extraction failure does not break Hermes shutdown/session end.

---

## 11. Project capsules

### 11.1 Project detection

Detect current project from:

1. `TERMINAL_CWD`
2. `os.getcwd()`
3. `git rev-parse --show-toplevel`
4. `git remote get-url origin`
5. fallback path hash

Project identity fields:

```python
project_id: str
repo_root: str | None
repo_remote: str | None
display_name: str
```

### 11.2 Capsule record

A project capsule is a special `ContextRecord` kind:

```text
kind = active_project_state
```

or a separate table if needed later.

Capsule sections:

- identity
- architecture summary
- verification commands
- known pitfalls
- user decisions
- recent work
- open questions

### 11.3 Retrieval behavior

When current project matches, capsule records should receive strong scope bonus. The capsule should often be retrieved instead of many scattered project records.

### 11.4 Definition of done

- Same git repo from subdir maps to same project id.
- Non-git directories get stable ids.
- Project capsule updates merge instead of append endlessly.
- Capsule prefetch stays under budget.

---

## 12. Security and safety

### 12.1 Content scanning

Before storing or injecting any record, scan for:

- prompt injection phrases
- hidden unicode/invisible characters
- exfiltration patterns
- obvious secrets/tokens/API keys
- private key blocks

Adapt patterns from Hermes `tools/memory_tool.py`.

### 12.2 Prompt safety

Automatic retrieval must never emit:

```text
System instruction:
Developer instruction:
Ignore previous instructions
```

as active instruction. If such content appears in a source, sanitize or block.

### 12.3 Trust handling

Retrieved records should include trust labels internally. Low-trust or remote-derived content should require higher relevance to inject.

### 12.4 Definition of done

- Injection-pattern records are rejected or sanitized.
- Secret-like records are rejected.
- Prefetch output strips dangerous fence tags or nested `<memory-context>` tags.
- Security tests cover obvious attack patterns.

---

## 13. Optional vector/hybrid phase

### 13.1 Vector backend abstraction

Do not hardcode one vector DB into core logic.

Interface:

```python
class VectorBackend:
    def is_available(self) -> bool: ...
    def upsert(record_id: str, text: str) -> None: ...
    def delete(record_id: str) -> None: ...
    def search(query: str, limit: int) -> list[VectorHit]: ...
```

### 13.2 Candidate backends

Preferred optional backends:

- `sqlite-vec` if packaging/install is stable.
- LanceDB if easiest local embedded vector backend.

FTS-only mode must remain fully supported.

### 13.3 What to embed

Embed compact `embedding_text`, not raw transcripts:

```text
{kind} {scope_project} {title} {summary} tags:{tags} entities:{entities}
```

### 13.4 Hybrid scoring

Vector results provide candidates and a score component, but exact/entity/project matching must still matter.

### 13.5 Definition of done

- Plugin works without vector deps.
- Vector tests mock backend scores for determinism.
- Fuzzy recall improves on eval fixtures.
- Exact recall does not regress.

---

## 14. Evaluation framework

### 14.1 Fixture files

`tests/fixtures/continuity_memory/records.jsonl`:

```json
{"id":"r_delegate_timeout","kind":"lesson_learned","scope_project":"guard-proxy","title":"delegate_task timeout before API calls","summary":"delegate_task can return status:timeout with api_calls:0 after exactly 300s; repeated delegation is usually wasteful, so work inline.","tags":["delegate_task","timeout","hermes"],"entities":["api_calls:0","300s"],"confidence":0.95,"importance":0.9}
```

`tests/fixtures/continuity_memory/queries.jsonl`:

```json
{"query":"the subagent timed out without doing anything again","scope_project":"guard-proxy","must_include":["r_delegate_timeout"],"must_not_include":[],"top_k":3}
```

### 14.2 Metrics

MVP tests:

- must-include appears in top-K
- must-not-include absent from top-K
- injected output under char budget
- deterministic order for ties

Later metrics:

- MRR
- recall@K
- precision@K
- budget-normalized utility

### 14.3 Required evaluation categories

- exact error strings
- fuzzy paraphrases
- project-scoped recall
- global user preference recall
- stale records
- low-confidence records
- distractor records
- unsafe records

### 14.4 Definition of done

- Evaluation test suite runs locally without Hermes credentials.
- FTS-only baseline has documented expected failures for truly semantic cases.
- Hybrid/vector phase improves those cases without breaking exact cases.

---

## 15. Phased implementation plan

## Phase 0 — Spec, RFC, eval design

**Goal:** Make the project repeatable before coding behavior.

### Tasks

1. Finalize this spec.
2. Write `README.md` with architecture and install target.
3. Create fixture records and queries.
4. Create initial failing tests for provider discovery, store, retrieval, tools.

### Definition of done

- Spec exists and future agents can follow it without chat context.
- Eval fixtures exist.
- Test skeleton exists and fails because implementation is absent.
- No production plugin behavior implemented before failing tests.

### Testing

```bash
python -m pytest tests/ -q
```

Expected initially: fail due missing implementation.

---

## Phase 1 — Plugin skeleton and Hermes loading

**Goal:** Hermes can discover and load a no-op `continuity` provider.

### Tasks

1. Create `continuity/__init__.py` with `ContinuityProvider`.
2. Add `register(ctx)`.
3. Implement `name`, `is_available`, `initialize`, `get_tool_schemas`, `handle_tool_call` for `continuity_status` only.
4. Add `plugin.yaml`.
5. Add install script to copy plugin into `$HERMES_HOME/plugins/continuity/`.

### Definition of done

- `load_memory_provider("continuity")` returns provider.
- `provider.is_available()` returns true.
- `initialize()` creates data directory.
- `continuity_status` returns valid JSON.

### Testing

- Unit tests for provider discovery with temp plugin path.
- Unit tests for `continuity_status`.
- Optional manual Hermes smoke test:

```bash
hermes config set memory.provider continuity
hermes chat -q "Use continuity_status and tell me if continuity memory is initialized" --toolsets memory
```

---

## Phase 2 — SQLite store and FTS retrieval

**Goal:** Store structured records and retrieve them deterministically using FTS + metadata.

### Tasks

1. Implement `ContextRecord` and `SourceRef` dataclasses.
2. Implement `ContinuityStore` migrations.
3. Implement CRUD.
4. Implement FTS indexing.
5. Implement retrieval scoring.
6. Implement eval fixture runner.

### Definition of done

- CRUD tests pass.
- FTS tests pass.
- Eval fixture exact/project tests pass.
- No vector dependencies required.

### Testing

```bash
python -m pytest tests/test_store.py tests/test_retrieval.py tests/test_eval_fixtures.py -q
```

---

## Phase 3 — Prefetch integration and budgeted context

**Goal:** `prefetch(query)` returns compact relevant memory under budget.

### Tasks

1. Load config defaults.
2. Implement project detection.
3. Implement `prefetch()` candidate retrieval.
4. Implement output formatting.
5. Enforce `max_records` and `max_chars`.
6. Log retrieval event to DB.

### Definition of done

- `prefetch()` returns empty for no match.
- `prefetch()` returns relevant compact context for fixture queries.
- Output never exceeds budget.
- Output includes source refs if configured.
- Output contains no raw transcript by default.

### Testing

```bash
python -m pytest tests/test_provider_prefetch.py tests/test_project.py tests/test_eval_fixtures.py -q
```

Manual smoke test with seeded DB:

```bash
hermes chat -q "the subagent timed out without doing anything again" --toolsets memory
```

Expected: Hermes receives/references relevant continuity memory.

---

## Phase 4 — Tools and inspectability

**Goal:** User/agent can inspect, search, add, delete, and debug records.

### Tasks

1. Implement `continuity_search`.
2. Implement `continuity_get`.
3. Implement `continuity_add`.
4. Implement `continuity_delete`.
5. Expand `continuity_status`.
6. Add debug info for last retrieval event.

### Definition of done

- All tools return JSON.
- Error cases are safe and clear.
- Added records are searchable.
- Deleted records no longer appear.
- Status shows DB path, counts, budget, vector state.

### Testing

```bash
python -m pytest tests/test_tools.py -q
```

---

## Phase 5 — Session observations and consolidation

**Goal:** Plugin learns from sessions without stuffing everything into prompt.

### Tasks

1. Implement `sync_turn()` observation storage.
2. Implement safe truncation/redaction for large turn content.
3. Implement conservative session-end extraction.
4. Implement candidate validation.
5. Implement dedupe/merge.
6. Store records with source refs.

### Definition of done

- Meaningful session fixture extracts expected records.
- Trivial session fixture extracts no records.
- Duplicate records merge.
- Unsafe extracted content is rejected.
- Failed extraction does not crash session shutdown.

### Testing

```bash
python -m pytest tests/test_extraction.py tests/test_security.py -q
```

---

## Phase 6 — Project capsules

**Goal:** Make repo continuation smart without injecting lots of old session records.

### Tasks

1. Implement git/path project identity.
2. Add capsule creation/update logic.
3. Merge project facts/decisions/pitfalls into capsule.
4. Prefer capsule retrieval when current project matches.
5. Add capsule status/search support.

### Definition of done

- Same repo from nested dirs maps to same project.
- Capsule summarizes project facts without endless append growth.
- Capsule is retrieved for project-scoped queries.
- Capsule output remains bounded.

### Testing

```bash
python -m pytest tests/test_project.py tests/test_project_capsule.py -q
```

---

## Phase 7 — Optional vector/hybrid retrieval

**Goal:** Improve fuzzy recall without making vector dependencies mandatory.

### Tasks

1. Define vector backend abstraction.
2. Add optional backend implementation.
3. Generate embedding text for records.
4. Add vector candidate generation.
5. Combine with FTS/entity/project scoring.
6. Add vector eval cases.

### Definition of done

- FTS-only mode still works without vector deps.
- Vector mode improves fuzzy eval cases.
- Exact eval cases do not regress.
- Tests use mocked vector backend for deterministic CI.

### Testing

```bash
python -m pytest tests/test_vectors.py tests/test_hybrid_retrieval.py tests/test_eval_fixtures.py -q
```

---

## Phase 7.5 — Built-in memory write mirroring

**Goal:** Make high-signal Hermes built-in memory writes searchable in continuity without changing user behavior.

Hermes built-in `MEMORY.md` / `USER.md` should remain tiny Tier 0 always-injected memory. This phase mirrors built-in memory writes into structured continuity records so the same curated facts can also be scoped, searched, source-backed, indexed, and included in project capsules.

### Behavior

Implement `ContinuityProvider.on_memory_write(action, target, content)`.

Supported actions:

- `add` — create or upsert a deterministic mirror record for `content`.
- `remove` — delete the deterministic mirror record for `content` when possible.
- `replace` — if only the new content is available, upsert the new mirror record and do not guess the old record id.

Supported targets:

- `user` — mirror as `user_preference` unless a conservative classifier can choose a better allowed kind.
- `memory` — mirror as `environment_fact` unless a conservative classifier can choose `lesson_learned`, `decision`, or `project_convention`.

Record requirements:

- deterministic id from `target` + normalized sanitized content hash, e.g. `mirror_user_<hash>` or `mirror_memory_<hash>`.
- `trust_level = built_in_memory_mirror`.
- source ref: `SourceRef(type="built_in_memory", id=target, label=f"Hermes memory {action}")`.
- `scope_project` should be current project display name when project context is available and content appears project-specific; global/user preferences may remain unscoped.
- content must pass the same secret redaction / prompt-injection rejection path used for observations.
- excessive content must be truncated before storage.
- vector indexing must happen through the provider's normal record upsert path when vector mode is enabled.

### Conservative classification rules

Do not use an LLM for this phase. Use deterministic rules only.

Suggested classifier:

- target `user` + preference-like wording (`prefers`, `likes`, `wants`, `call them`, `timezone`) → `user_preference`.
- target `memory` + `lesson`, `gotcha`, `pitfall`, `beware`, `workaround`, `quirk` → `lesson_learned`.
- target `memory` + `decided`, `declined`, `chose`, `decision` → `decision`.
- target `memory` + `uses`, `project`, `repo`, `convention`, `test`, `verify`, `build` → `project_convention` when project-scoped, otherwise `environment_fact`.
- fallback: target `user` → `user_preference`; target `memory` → `environment_fact`.

### Tasks

1. Add deterministic mirror id helper and content normalization helper.
2. Add conservative memory-write classifier.
3. Implement `on_memory_write()` add/remove/replace behavior.
4. Ensure mirrored records use source refs and `built_in_memory_mirror` trust.
5. Route mirrored upserts through vector-aware provider helper.
6. Update project capsule generation to naturally include mirrored project records.
7. Add tests for add, remove, replace, classification, redaction, scope, retrieval, and vector indexing.
8. Add `docs/PHASE7_5.md` documenting behavior and non-goals.

### Definition of done

- Built-in memory writes create searchable continuity records.
- Removed built-in memory content deletes the matching mirrored record when deterministic id can be computed.
- Mirrored records are source-backed as `built_in_memory`.
- Mirroring does not duplicate skill contents or transcript blobs.
- Secrets are redacted and obvious prompt-injection-like content is rejected.
- FTS-only and vector-enabled modes both pass.
- Existing retrieval and project capsule tests do not regress.

### Testing

```bash
uv run ruff check .
uv run pytest tests/test_memory_mirror_phase7_5.py tests/test_provider_phase7.py tests/test_project_capsule_phase6.py -q
uv run pytest tests/ -q
```

---

## Phase 7.6 — Skill links for continuity records

**Goal:** Connect semantic continuity memories to procedural Hermes skills without copying skill contents into the memory store.

A continuity memory captures what is true or what happened. A Hermes skill captures how to act. This phase lets a memory say "this skill was relevant to this memory" so retrieval can suggest procedural context when a remembered situation recurs.

### Non-goals

- Do not store skill bodies in SQLite.
- Do not automatically load skills from the memory provider.
- Do not build a general memory graph or broad memory-to-memory spreading activation system in this phase.
- Do not persist weak embedding-similarity links between every related record.

### Schema

Add a sparse skill-link table:

```sql
CREATE TABLE IF NOT EXISTS context_record_skill_links (
  record_id TEXT NOT NULL,
  skill_name TEXT NOT NULL,
  reason TEXT,
  confidence REAL NOT NULL DEFAULT 0.5,
  source TEXT NOT NULL DEFAULT 'agent_observed',
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  PRIMARY KEY(record_id, skill_name),
  FOREIGN KEY(record_id) REFERENCES context_records(id) ON DELETE CASCADE
);
```

`skill_name` should use canonical Hermes skill names such as:

```text
software-development/systematic-debugging
devops/openbsd-rust-dev-loop
github/github-pr-workflow
```

### Behavior

- `continuity_add` may accept optional `skill_links`.
- `continuity_get` returns skill links for the record.
- `continuity_search` returns skill links for each result.
- `prefetch()` may include at most 1–2 compact skill hints per selected memory, subject to the same prompt budget.
- Skill hints should be informational, not instructions, e.g. `Related skills: devops/openbsd-rust-dev-loop`.
- Skill links should be explicit or high-confidence only.

### Link model

Suggested `SkillLink` fields:

```python
@dataclass(frozen=True)
class SkillLink:
    record_id: str
    skill_name: str
    reason: str | None = None
    confidence: float = 0.5
    source: str = "agent_observed"
    created_at: str = field(default_factory=utc_now)
    last_used_at: str | None = None
```

Allowed `source` values should be constrained at the model layer, for example:

```text
explicit_user
agent_observed
session_extracted
built_in_memory_mirror
```

### Tasks

1. Add `SkillLink` model and validation.
2. Add schema migration for `context_record_skill_links`.
3. Add store methods: `upsert_skill_link()`, `delete_skill_link()`, `list_skill_links(record_id)`, and optional `replace_skill_links(record_id, links)`.
4. Extend `continuity_add` to accept optional `skill_links` and persist them.
5. Extend `continuity_get` and `continuity_search` responses with `skill_links`.
6. Extend prefetch formatting with compact, budgeted `Related skills:` lines.
7. Add tests for add/get/search/prefetch/delete cascade behavior.
8. Add `docs/PHASE7_6.md` documenting skill-link semantics and non-goals.

### Definition of done

- Records can have zero or more explicit skill links.
- Skill links are returned by inspection/search tools.
- Prefetch can show compact related-skill hints without blowing budget.
- Deleting a record removes its skill links.
- No skill content is duplicated in continuity memory.
- Existing memory retrieval behavior does not regress.

### Future memory-to-memory links

Memory-to-memory links are deferred. If added later, prefer a separate sparse edge table with explicit relation types such as `supports`, `supersedes`, `contradicts`, `duplicates`, `derived_from`, `follow_up`, and `resolved_by`.

Do not persist weak similarity links by default. Similarity should usually remain a query-time retrieval/scoring concern.

If a future phase adds relationship strength, use `strength` or `confidence` with strict caps such as:

```text
max_link_hops = 1
min_link_strength = 0.7
max_related_records = 2
```

### Testing

```bash
uv run ruff check .
uv run pytest tests/test_skill_links_phase7_6.py tests/test_tools_phase4.py tests/test_prefetch_phase3.py -q
uv run pytest tests/ -q
```

---

## Phase 8 — Packaging, documentation, and release

**Goal:** Make this usable as a GitHub plugin, not a local hack.

### Tasks

1. Write installation docs.
2. Write configuration docs.
3. Write troubleshooting docs.
4. Add example eval dataset.
5. Add `scripts/install.sh`.
6. Add CI workflow.
7. Tag initial release.

### Definition of done

- Fresh Hermes user can install plugin from README.
- Plugin can be enabled with `memory.provider: continuity`.
- Tests pass in CI.
- README clearly states limitations and safety model.

### Testing

Manual clean install test in temp Hermes home:

```bash
export HERMES_HOME=$(mktemp -d)
./scripts/install.sh
hermes config set memory.provider continuity
hermes memory status
```

---

## 16. Implementation discipline for future agents

Future agents implementing this spec must follow:

1. Use TDD for each behavior.
2. Keep tasks small.
3. Run targeted tests after each task.
4. Run broader suite before finishing phase.
5. Do not add vector search before FTS/store/evals are stable.
6. Do not alter Hermes upstream unless the plugin API truly blocks the work.
7. Prefer plugin-only solutions.
8. If upstream change is needed, document exact reason and propose minimal patch.

---

## 17. Known upstream limitations and workarounds

### Limitation: only one external memory provider

Workaround: plugin is selected provider. Do not require Honcho/Mem0 concurrently.

Future upstream idea: provider composition or multiple external providers.

### Limitation: `on_pre_compress()` return may not affect compression prompt

Workaround: use side effects only; extract/store before compression.

Future upstream idea: wire returned text into compression prompt.

### Limitation: `prefetch(query)` gets only current user message

Workaround: plugin detects cwd/git/project itself.

Future upstream idea: pass runtime context object to provider hooks.

### Limitation: no first-class `/context` slash command

Workaround: expose provider tools and optional plugin CLI.

Future upstream idea: generic context debug UI.

---

## 18. Release criteria

### Alpha release

- Plugin loads.
- SQLite store works.
- Manual add/search/status tools work.
- FTS retrieval and prefetch under budget work.
- Basic docs exist.

### Beta release

- Session consolidation works.
- Project capsules work.
- Eval fixtures pass.
- Security scanner blocks obvious unsafe records.
- CI passes.

### Stable v1.0

- Robust install docs.
- Crash-safe turn observations.
- Good retrieval debug story.
- Optional vector backend if stable, otherwise explicitly deferred.
- Proven in real Hermes sessions without prompt bloat.

---

## 19. Open questions

1. Should extraction use Hermes' auxiliary LLM client, or remain heuristic/plugin-local for portability?
2. Should raw session observations be encrypted or expire by default?
3. What is the default retention policy?
4. Should project capsules be user-editable markdown as well as DB records?
5. Should `continuity_expand` integrate with Hermes session DB directly or only plugin-stored observations?
6. Which vector backend is most compatible with Hermes' packaging constraints?
7. How should the plugin avoid duplicating facts already in `MEMORY.md` / `USER.md` while still indexing them?

---

## 20. Minimal next action

For the next implementation session, start with Phase 0:

1. Create standalone repo or plugin directory.
2. Add fixture records/queries.
3. Add failing provider discovery and store tests.
4. Implement only enough skeleton to make discovery/status tests pass.

Do not implement retrieval before tests and fixtures exist.
