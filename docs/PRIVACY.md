# Privacy guide

Hermes Continuity Memory stores durable memory locally. That makes it useful, but it also means operators should understand what can be stored, where it lives, and how to inspect or delete it.

## What is stored

Continuity may store:

- explicit records added with `continuity_add`;
- compact records mirrored from Hermes built-in memory writes;
- marker-extracted records from phrases such as `Remember:`, `Lesson learned:`, and `Decision:`;
- sanitized per-turn observations if enabled;
- imported corpus-derived records and source references;
- retrieval event logs for diagnostics;
- optional vector rows derived from record text;
- association graph edges between related records.

Records can include user preferences, project state, decisions, environment facts, source references, and debugging lessons.

## Where data is stored

Runtime data is stored in SQLite under:

```text
${HERMES_HOME:-$HOME/.hermes}/continuity/continuity.db
```

Plugin code is installed separately under:

```text
${HERMES_HOME:-$HOME/.hermes}/plugins/continuity/
```

Deleting plugin code does not delete the runtime database.

## What can enter prompts

For each turn, Hermes can ask the provider for relevant context. The provider may inject a compact memory block containing selected record summaries and optional source refs/scores.

Prompt injection is bounded by:

- `max_records`;
- `max_chars`;
- lifecycle filtering;
- retrieval gates;
- optional pinned Tier 0 limits.

Continuity records are rendered as background facts, not as new instructions. A model can still be influenced by recalled text, so store compact, trustworthy records.

## What is not protected

Continuity is not:

- encrypted storage;
- comprehensive DLP;
- a multi-user access-control boundary;
- a secret manager;
- a legal/compliance system;
- a guarantee that stale or incorrect facts will never be retrieved.

Anyone who can read the SQLite database file can inspect stored continuity data.

## Secret handling

Supported write paths redact or reject some obvious secret patterns and prompt-injection-like content. This is a safety net, not a guarantee.

Do not intentionally store:

- API keys;
- passwords;
- private keys;
- session cookies;
- access tokens;
- regulated personal data;
- confidential raw logs;
- private source text you do not want summarized into prompts.

If a secret might have been stored, delete the affected record or wipe the database. Also rotate the secret outside this plugin.

## Inspect records

Use:

```text
continuity_search(query="term", include_stale=true)
continuity_get(id="record_id")
continuity_debug_retrieval(query="exact query")
```

Use `include_stale=true` when auditing archived, retracted, or expired records.

## Delete or archive records

Archive ordinary stale records:

```text
continuity_archive(id="record_id", reason="no longer current")
```

Restore if needed:

```text
continuity_restore(id="record_id")
```

Hard delete sensitive or invalid records:

```text
continuity_delete(id="record_id")
```

## Wipe all continuity data

Warning: this removes the local continuity memory database.

```bash
rm -rf "${HERMES_HOME:-$HOME/.hermes}/continuity"
```

This does not remove plugin code or edit Hermes config.

## Backup privacy

Database backups contain the same private data as the live database. Store backups with the same care.

```bash
cp "${HERMES_HOME:-$HOME/.hermes}/continuity/continuity.db" continuity.db.backup
```

Do not commit backups to git.

## Corpus ingestion privacy

Corpus ingestion is review-first and does not mutate the live database until explicit import.

Safe default flow:

1. Run ingestion into a temporary output directory.
2. Review `candidate-records.jsonl`, `pending-records.jsonl`, `rejected-candidates.jsonl`, and `review.md`.
3. Validate import into a temporary DB.
4. Import only approved records with `--apply`.

Do not ingest private documents unless you are comfortable with distilled records and source references being stored in the continuity database.

LLM extraction is explicit opt-in. If you use an LLM extractor, source text and model output should be treated as untrusted data and reviewed before import.

## Public demos and test fixtures

The repository ships synthetic JSONL demo records rather than a real memory DB. This is intentional:

- JSONL is auditable in diffs;
- no private runtime database is published;
- fixtures can be scanned by secret scanners;
- demo behavior is reproducible after checkout.

Keep future public examples synthetic.

## Recommended public-release hygiene

Before publishing a repo or opening a PR:

```bash
git status --short --branch
git ls-files | grep -E 'continuity\.db|\.sqlite|\.env|id_rsa|dist/|\.venv/' || true
gitleaks detect --no-git --redact --verbose .
gitleaks detect --redact --verbose --source .
```

Also search tracked files for local/private markers that are not secrets but still should not be public, such as local absolute paths or real user/project names in fixtures.
