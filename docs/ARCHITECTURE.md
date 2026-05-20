# Architecture overview

Hermes Continuity Memory is a local-first memory provider for Hermes Agent. It stores many durable facts outside the prompt and activates only a small, relevant subset for each turn.

The design goal is **sparse memory activation**: keep the model prompt small, make retrieval inspectable, and treat recalled memory as advisory context rather than instructions.

## Mental model

```text
User turn
  │
  ▼
Hermes asks the memory provider for relevant context
  │
  ▼
Continuity retrieves candidate records from SQLite FTS, metadata, optional vectors,
optional reranking, and optional association-graph expansion
  │
  ▼
Retrieval gates reject weak/noisy/stale candidates
  │
  ▼
A compact memory block is injected into the prompt within max_records/max_chars
```

Continuity is not a transcript chunker and is not a guarantee of perfect recall. It is a structured, inspectable layer for durable facts, project state, decisions, lessons learned, and other compact context worth retrieving later.

## Core data model

The central object is `ContextRecord`, defined in `continuity/models.py`.

A record includes:

- `id` — stable record identifier.
- `kind` — record type, such as `user_preference`, `decision`, `lesson_learned`, `environment_fact`, `project_convention`, `active_project_state`, or corpus-derived kinds.
- `title`, `summary`, and optional `details` — compact human-readable memory content.
- scopes — optional `scope_project`, `scope_user`, `scope_repo`, and `scope_profile`.
- `tags` and `entities` — retrieval anchors and metadata.
- quality signals — `confidence`, `importance`, and `trust_level`.
- lifecycle fields — active/archive/retract/expiry/supersession metadata.
- `sources` — references back to built-in memory writes, corpus segments, files, or other origins.
- optional `skill_links` — compact hints that a Hermes skill may be relevant.

Records are intended to be small and durable. Large procedures belong in skills or source documents; raw conversation history belongs in session search.

## Storage

The provider stores runtime data in SQLite under:

```text
${HERMES_HOME:-$HOME/.hermes}/continuity/continuity.db
```

`continuity/store.py` owns schema creation, migrations, and persistence for:

- context records;
- SQLite FTS indexes;
- optional vector rows;
- source corpus documents and segments;
- association graph edges;
- retrieval event logs;
- provider state, such as maintenance-cycle timestamps.

SQLite keeps the default install dependency-free and easy to inspect, back up, or delete.

## Retrieval path

`continuity/retrieval.py` combines several retrieval signals:

1. **SQLite FTS5** over title, summary, details, tags, entities, and source-ish text.
2. **Metadata scoring** for project scope, tags, entities, confidence, importance, trust, and text anchors.
3. **Optional vector retrieval** using either dependency-free `sqlite-hash` vectors or local `sentence-transformers` embeddings.
4. **Optional reranking** with a local cross-encoder backend.
5. **Optional association graph expansion** to rescue related context that did not directly match the query.
6. **Retrieval gates** that reject weak vector-only hits, generic memory-meta collisions, low-information follow-ups, incompatible facets, stale records, and weak graph activations.

Normal prefetch output is then bounded by `max_records` and `max_chars`.

## Memory write path

Continuity can receive records through several paths:

```text
continuity_add tool
  └─ validate and store an explicit ContextRecord

Hermes built-in memory write
  └─ on_memory_write() mirrors high-signal writes into structured records

Session end
  └─ marker extraction from phrases like "Remember:", "Lesson learned:", and "Decision:"

Corpus ingestion
  └─ review-first JSONL candidates are validated and explicitly imported
```

All write paths should keep records compact, source-linked, and free of secrets. Obvious secret patterns are redacted or rejected in supported paths, but this is not comprehensive DLP.

## Prompt injection model

Continuity records are rendered as background context, not instructions. The prompt block labels direct hits and lower-confidence associated context separately.

Safety controls include:

- compact prompt budgets;
- lifecycle filtering: archived, retracted, and expired records are excluded from normal retrieval;
- trust and source metadata;
- conservative write-path filtering for obvious prompt-injection-like content;
- debug tools to explain why records were selected or rejected.

Callers should still verify important facts against source references or live tools.

## Tier 0 pinned records

The provider can include a tiny set of high-trust records in the system prompt every turn. This is the continuity replacement for a small always-on memory kernel.

Pinned records are controlled by `pinned_system_prompt` settings:

```yaml
memory:
  continuity:
    pinned_system_prompt:
      enabled: true
      include_records: true
      max_chars: 1200
      max_records: 5
      kinds: [user_preference, project_convention]
      min_importance: 0.75
```

Keep Tier 0 small and auditable. Long-tail memory should be retrieved per turn instead.

## Corpus ingestion architecture

Corpus ingestion is intentionally review-first, not automatic background indexing.

```text
Source files
  ▼
SourceDocument inventory
  ▼
SourceSegment extraction
  ▼
CandidateRecord generation
  ▼
quality/safety/dedupe/review
  ▼
approved JSONL
  ▼
explicit import into continuity.db
```

Imported records keep source references so `continuity_hydrate` can recover supporting source text for verification.

See `docs/CORPUS_INGESTION.md` for commands and review flow.

## Maintenance lifecycle

Records can be:

- active;
- archived;
- retracted;
- expired;
- superseded by newer records.

The maintenance tools prefer conservative reporting and archiving over deletion:

- `continuity_prune_stale`
- `continuity_archive`
- `continuity_restore`
- `continuity_dream`

Hard deletion is available for clearly wrong or sensitive records.

## Extension points

Useful places to start:

- Add or change config: `continuity/config.py`
- Change retrieval ranking or gates: `continuity/retrieval.py`
- Change persistence or migrations: `continuity/store.py`
- Add a tool: `continuity/tools.py` plus provider dispatch in `continuity/__init__.py`
- Change memory mirroring: `continuity/memory_mirror.py`
- Change ingestion: `continuity/ingest/`
- Change public docs: `docs/`

## Non-goals

Continuity is not:

- a multi-user access-control boundary;
- encrypted storage;
- comprehensive data-loss prevention;
- automatic background indexing of private files;
- raw transcript RAG;
- a replacement for Hermes skills or live verification tools.
