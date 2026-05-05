# Continuity Memory GitHub + Blog Release Checklist

> **For Hermes:** Use `multi-step-spec-execution` or `subagent-driven-development` when working through this across sessions. Load `hermes-continuity-memory`, `requesting-code-review`, and relevant GitHub skills before implementation/release work.

**Goal:** Prepare the Hermes Continuity Memory plugin for a credible public GitHub release and blog post.

**North Star:** Make Hermes Agent more useful with smaller/local models by providing a very large external knowledge store with accurate, relevant, surgical retrieval that keeps the model context small — roughly “MoE-style routing for agent memory: many memories stored, few memories activated.”

**Current checkpoint from 2026-05-05:**
- Live continuity provider is initialized and working.
- Vector retrieval, reranker, and association graph are available in the live gateway.
- Dreaming API is live; scheduled dreaming is currently disabled in config.
- Live plugin files and repo files were byte-for-byte synced for the key changed files checked on 2026-05-05.
- `uv run ruff format --check .`, `uv run ruff check .`, `uv run pytest tests/ -q`, and `python -m compileall continuity tests` passed.
- `uv build` passed and the wheel included `continuity/plugin.yaml` and `continuity/py.typed`.
- `./scripts/smoke-test.sh` initially failed in the isolated loader/search assertion: the inserted smoke-test record was added, but `continuity_search` returned `results: []` for `patch lint rust cargo check`.
- 2026-05-05 update: Task 1 and Task 2 are complete. Root cause was the smoke record title `Phase 8 smoke test memory`: tokens like `memory`/`record` triggered the memory-system record gate for a non-meta query. The smoke title was changed to `Phase 8 smoke check`, and `./scripts/smoke-test.sh` now passes.
- 2026-05-05 update: Full local gate passed after the smoke fix: `uv run ruff format --check .`, `uv run ruff check .`, `uv run pytest tests/ -q` (`114 passed`), `python -m compileall continuity tests`, `./scripts/smoke-test.sh`, `uv build`, and wheel inspection for `continuity/plugin.yaml` + `continuity/py.typed`.
- Repo had uncommitted changes including dream functionality, tests, docs/assets, docs/plans, and the smoke-test fix.

---

## Phase 1 — Release blockers

### Task 1: Fix isolated smoke test failure

**Objective:** Make `./scripts/smoke-test.sh` pass from a fresh temporary `HERMES_HOME`.

**Files likely involved:**
- Modify: `scripts/smoke-test.sh`
- Possibly modify: `continuity/retrieval.py`, `continuity/store.py`, `continuity/tools.py`, or config defaults if the failure reveals a real isolated-loader bug.
- Test: existing smoke script plus targeted unit test if a product bug is found.

**Repro command:**
```bash
cd /root/hermes-continuity-memory
./scripts/smoke-test.sh
```

**Known failure detail:**
The smoke script successfully adds `r_phase8_smoke`, but then:
```json
{
  "success": true,
  "query": "patch lint rust cargo check",
  "results": []
}
```

**Debug checklist:**
- Verify whether smoke test loads the installed plugin from Hermes plugin loader or the repo package.
- Verify vector backend/config used in the smoke test: currently `{"vector": {"enabled": true, "backend": "sqlite-hash"}}`.
- Inspect whether `scope_project=ROOT.name` is boosting or filtering unexpectedly.
- Check whether reranker/facet gates reject the new record in isolated mode.
- Use `continuity_debug_retrieval` equivalent via `provider.handle_tool_call` if available.
- Decide whether the smoke script query/expectation is stale or whether retrieval has a real bug.

**Acceptance criteria:**
- `./scripts/smoke-test.sh` passes.
- If retrieval behavior was changed, add/adjust unit tests so the same failure cannot recur.

### Task 2: Run full local gate after smoke fix

**Objective:** Verify the repo is cleanly releasable after the smoke-test fix.

**Commands:**
```bash
cd /root/hermes-continuity-memory
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/ -q
python -m compileall continuity tests
./scripts/smoke-test.sh
uv build
python - <<'PY'
import glob, zipfile
wheel = sorted(glob.glob('dist/*.whl'))[-1]
print(wheel)
with zipfile.ZipFile(wheel) as z:
    names = set(z.namelist())
for required in ['continuity/plugin.yaml', 'continuity/py.typed']:
    assert required in names, f'missing {required}'
    print(required, 'OK')
PY
```

**Acceptance criteria:**
- All commands pass.
- Wheel contains required plugin/type marker files.

### Task 3: Commit the release-blocker work

**Objective:** Commit the synced repo state after tests pass.

**Commands:**
```bash
cd /root/hermes-continuity-memory
git status --short
git diff --stat
git add continuity tests scripts docs README.md CHANGELOG.md pyproject.toml uv.lock
# adjust paths as needed after inspecting status
git commit -m "feat: add continuity dream maintenance cycle"
```

**Acceptance criteria:**
- Working tree is clean or only contains intentionally ignored/generated files.
- Commit message reflects actual contents.

---

## Phase 2 — Public repo hygiene

### Task 4: Secret and artifact scan

**Objective:** Ensure nothing private or accidental is published.

**Commands:**
```bash
cd /root/hermes-continuity-memory
# If available:
gitleaks detect --source . --no-git
gitleaks detect --source .

# Also inspect tracked files:
git status --ignored --short
git ls-files
```

**Check for:**
- API keys, Discord tokens, model provider keys, private URLs.
- Local DBs, sessions, logs, `.venv`, caches, `__pycache__`, `.pytest_cache`, build artifacts.
- Personal/local paths that should be generalized.

**Acceptance criteria:**
- Secret scan clean or documented false positives.
- `.gitignore` excludes generated/private artifacts.

### Task 5: Verify install story from scratch

**Objective:** A fresh user can install and verify the plugin without knowing our live setup.

**Commands/flow:**
```bash
TMP_HOME=$(mktemp -d)
export HERMES_HOME="$TMP_HOME"
cd /root/hermes-continuity-memory
./scripts/install.sh
./scripts/smoke-test.sh
```

**Docs to verify/update:**
- `README.md`
- `docs/INSTALL.md`
- `docs/CONFIGURATION.md`
- `docs/TROUBLESHOOTING.md`

**Acceptance criteria:**
- Install steps are copy-pasteable.
- Required Hermes Agent version/commit or plugin-loader assumptions are documented.
- Minimal config example works.

### Task 6: Public README positioning pass

**Objective:** Make README lead with the small-model / sparse-memory-routing thesis.

**README must communicate:**
- Continuity is not “just vectors.”
- It is a local structured memory layer for Hermes Agent.
- It helps smaller/local models by keeping a large knowledge base outside the prompt and activating only a few relevant records.
- Built-in memory remains a tiny trusted kernel; continuity is the scalable contextual layer.
- Session search is the raw archive; skills remain procedural memory.
- Retrieval is advisory, inspectable, and bounded by prompt budget.

**Potential tagline:**
> MoE-style routing for agent memory: many memories stored, few memories activated.

**Acceptance criteria:**
- README explains the product thesis in the first screenful.
- README includes install, config, quickstart, tools, limitations, and safety notes.

---

## Phase 3 — Retrieval quality confidence

### Task 7: Lock down retrieval regression tests

**Objective:** Prove the router is precise enough for the public claim.

**Add/verify tests for:**
- Low-information queries retrieve no context: `ok good`, `how about now`, `can you test and see if it's better now?`.
- Unrelated generic questions retrieve no context: weather, recipes, generic programming questions.
- Software-framework queries do not retrieve Framework Desktop/hardware records.
- Framework Desktop/hardware queries do retrieve personal hardware records when anchored.
- Memory-system queries retrieve continuity/memory-system records.
- User preference queries retrieve user preference records even when reranker scores are low.
- Anchored implicit-context questions can use association graph rescue.
- Association graph does not activate from weak/generic activation seeds.
- Archived/stale records are excluded by default.

**Files likely involved:**
- `tests/test_association_graph.py`
- `tests/test_tools_phase*.py`
- new test file if useful: `tests/test_retrieval_regressions.py`

**Acceptance criteria:**
- Regression tests fail before a bug fix and pass after.
- Full test suite passes.

### Task 8: Add small-model-oriented evaluation examples

**Objective:** Provide credible evidence for the blog/README claim.

**Create an eval doc or script covering:**
- Same small model, same question, with and without continuity.
- Prompt/context size difference.
- Retrieved record count/chars.
- Whether answer was correct.
- False-positive/no-memory cases.

**Suggested scenarios:**
| Scenario | No continuity | Continuity | Expected behavior |
|---|---|---|---|
| Project path recall | asks user/guesses | retrieves live plugin path | correct path/context |
| Gateway/dreaming status | vague | retrieves continuity status/project record | accurate status framing |
| User preference query | misses | retrieves preference | applies preference |
| Framework ambiguity | may confuse | gates correctly | avoids false hardware/software match |
| Unrelated query | no memory | no memory | no noisy injection |

**Acceptance criteria:**
- At least one reproducible before/after demo exists.
- Results are honest and include limitations/failures.

---

## Phase 4 — Dreaming/staleness story

### Task 9: Decide and document dream status

**Objective:** Avoid overselling dream maintenance.

**Decision options:**
1. Document as manual/experimental:
   - `continuity_dream(mode="report")` works now.
   - Archive modes soft-archive only.
   - Scheduled dream is config-supported but off by default.
2. Enable scheduled report-only dream in example config:
   - `dream.enabled: true`
   - `mode: report`
   - explain that Hermes checks due time on initialize/sync_turn, not via independent wall-clock daemon.

**Docs to update:**
- `README.md`
- `docs/CONFIGURATION.md`
- `docs/TROUBLESHOOTING.md`

**Acceptance criteria:**
- Docs clearly distinguish manual, scheduled-on-turn, and external cron/service scheduling.
- No implication of hard deletes or autonomous destructive behavior.

### Task 10: Add dream report sample

**Objective:** Show users what dream maintenance does.

**Include sample output showing:**
- record counts before/after
- stale candidates
- archived IDs
- deleted IDs always empty for dream
- notes

**Acceptance criteria:**
- Sample output is realistic and says whether it is mutating.

---

## Phase 5 — Blog post assets

### Task 11: Create architecture and live-query retrieval diagrams

**Objective:** Explain the system visually, including both the general architecture and at least one real debug-query path.

**General architecture diagram should show:**
```text
Conversation / memory writes
    ↓
Structured continuity records in local SQLite
    ↓
FTS + vectors + tags/entities/scopes
    ↓
facet gates + reranker
    ↓
optional association graph
    ↓
top 1–5 compact records
    ↓
small model context window
```

**Live-query diagram should show:**
```text
User query
    ↓
Retrieval engine / query analysis
    ↓
DB search request
    ↓
Continuity DB returns candidate rows
    ↓
Candidate scoring + gates + reranker
    ↓
Selected records / rejected candidates / graph-cut neighbors
    ↓
Final bounded <memory-context>
    ↓
Small model sees query + tiny advisory memory block
```

**Current generated examples:**
- General diagram: `docs/assets/continuity-memory-activation-diagram.html` and `.png`
- Live continuity-meta query diagram: `docs/assets/continuity-live-retrieval-example.html` and `.png`
- Live sailing query diagram with generalized personal details: `docs/assets/continuity-sailing-query-retrieval-path.html` and `.png`

**Acceptance criteria:**
- Diagram is usable in README/blog.
- Caption emphasizes sparse activation and small context.
- Text is manually wrapped/bounded inside boxes.
- Arrows clearly show what talks to the DB: retrieval engine → DB search → candidate rows returned.
- Use at least one non-continuity-engine example query so readers do not confuse query content with explanatory labels.

### Task 11b: Consider a retrieval-debug graph tool

**Objective:** Evaluate turning the diagram generator into a first-class debugging tool for continuity retrieval.

**Proposed CLI/tool behavior:**
```bash
continuity-debug-graph \
  --query "What kind of trailerable sailboat should I look at for local lakes?" \
  --db ~/.hermes/continuity/continuity.db \
  --out docs/assets/retrieval-debug.html \
  --redact personal
```

**Tool should render:**
- query tokens / expanded anchors
- DB candidate generation path
- selected records with scores, roles, and reasons
- rejected records grouped by reason
- activation seeds and direct seeds
- association edges fired
- included neighbors vs cut neighbors
- final prompt/context budget summary
- optional privacy modes: full, titles-only, grouped, redacted

**Acceptance criteria:**
- Feasibility decision documented.
- If implemented, output is deterministic HTML/SVG with no external service dependency.
- Privacy mode defaults to redacting or grouping personal records.

### Task 12: Draft blog post

**Objective:** Publish a credible explanation of why the plugin exists and what it does.

**Working title ideas:**
- “Sparse Memory Activation for Small Agent Models”
- “MoE-Style Routing for Agent Memory”
- “Making Small Agent Models Useful with Surgical Long-Term Memory”

**Required sections:**
1. Problem: small/local models have limited context and weak long-transcript use.
2. Goal: large external knowledge store without prompt bloat.
3. Analogy: MoE-style memory routing.
4. Architecture: records, metadata, FTS/vector/reranker, association graph, lifecycle/dreaming.
5. Demo: with/without continuity on a smaller model.
6. Debuggability: status/search/debug tools.
7. Limitations: retrieval misses, noisy retrieval, stale memory, current facts still need tools.
8. Status: alpha/experimental but dogfooded.
9. Link to GitHub.

**Acceptance criteria:**
- Blog is honest about limitations.
- Claims are supported by tests/demo output.
- Does not claim perfect recall or production maturity.

---

## Phase 6 — Final release

### Task 13: Final pre-release verification

**Objective:** Last gate before publishing.

**Commands:**
```bash
cd /root/hermes-continuity-memory
git status --short
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/ -q
python -m compileall continuity tests
./scripts/smoke-test.sh
uv build
```

**Acceptance criteria:**
- All checks pass.
- Working tree clean.
- README/docs are current.

### Task 14: Tag and publish repository

**Objective:** Prepare public GitHub release.

**Steps:**
- Confirm remote target with user before creating/pushing any remote.
- Create release tag if desired, e.g. `v0.1.0-alpha`.
- Push repo/tag only after explicit approval.

**Acceptance criteria:**
- Public repo contains clean source, docs, tests, license, changelog, security policy, and install instructions.

### Task 15: Publish blog post

**Objective:** Publish the announcement/explanation after GitHub is ready.

**Acceptance criteria:**
- Blog links to public repo.
- Blog includes demo/eval evidence.
- Blog labels status accurately as alpha/experimental/dogfooded.

---

## Definition of done

I would feel comfortable publishing when these are true:

- [ ] `./scripts/smoke-test.sh` passes from a clean temp home.
- [ ] Full quality gate passes: ruff format, ruff check, pytest, compileall, smoke test, build.
- [ ] Live/repo source parity has been checked after any live plugin edits.
- [ ] Secret scan is clean.
- [ ] README leads with small-model sparse-memory-routing thesis.
- [ ] Install/config docs are verified from scratch.
- [ ] Retrieval regression tests cover known noisy cases.
- [ ] Dreaming docs accurately describe manual/scheduled behavior.
- [ ] At least one small-model before/after demo supports the main claim.
- [ ] Repo changes are committed cleanly.
- [ ] User explicitly approves any push/publication steps.
