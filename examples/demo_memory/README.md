# Demo Continuity Memory Corpus

This directory contains a small, synthetic/public continuity-memory corpus for trying the plugin without using a real personal memory database.

Files:

- `records.jsonl` — static `ContextRecord` objects loaded into a temporary SQLite DB.
- `queries.jsonl` — retrieval expectations for the demo script.

Run from the repository root:

```bash
python scripts/demo-retrieval.py
```

The demo creates a temporary `HERMES_HOME`, initializes the continuity provider with the dependency-free `sqlite-hash` vector backend, loads these records, runs retrieval expectations, exercises add/search/archive/restore, runs a report-only dream cycle, and deletes the temporary data when done.

No real user memories or private data are included here.
