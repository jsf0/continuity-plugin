# Public demo walkthrough

The repository includes a synthetic demo corpus so you can try retrieval without using a real memory database.

The demo is intentionally public and synthetic. It does not include real user memories, private project state, credentials, or a committed SQLite database.

## What the demo shows

The demo exercises the complete lightweight path:

- load reviewable JSONL records into a temporary `HERMES_HOME`;
- run expected retrieval queries;
- show expected vs actual hits;
- exercise add/search/archive/restore/delete lifecycle operations;
- run a report-only maintenance cycle;
- demonstrate the compact prompt context that a small model would receive.

## Files

```text
examples/demo_memory/records.jsonl   synthetic public records
examples/demo_memory/queries.jsonl   expected retrieval behavior
examples/demo_memory/README.md       fixture notes
scripts/demo-retrieval.py            Python demo runner
scripts/demo-retrieval.sh            uv-aware shell wrapper
scripts/demo-small-model-context.py  before/after prompt-context demo
```

JSONL fixtures are used instead of a committed database because they are easy to audit in diffs, portable across SQLite versions, and safe to scan for secrets.

## Run the retrieval demo

From the repository root:

```bash
./scripts/demo-retrieval.sh
```

Quiet mode is useful for CI:

```bash
./scripts/demo-retrieval.sh --quiet
```

Expected final line:

```text
demo retrieval ok
```

The demo creates a temporary home and removes it when done. It does not read or modify your real continuity database.

## Run the small-model context demo

```bash
python scripts/demo-small-model-context.py
```

Or with `uv`:

```bash
uv run python scripts/demo-small-model-context.py
```

Expected final line:

```text
small model context demo ok
```

This is not a benchmark and does not call an LLM. It prints a reproducible before/after prompt-context example:

- without continuity, the model has no project memory;
- with continuity, one compact relevant record is retrieved and rendered into the prompt context.

## What to look for

In the retrieval demo, confirm that:

- expected `must_include` records appear in the top results;
- negative/noise expectations are not selected;
- archived records stay out of normal retrieval;
- archive/restore/delete operations work;
- report-only maintenance does not mutate unexpectedly.

In the small-model context demo, look for the bounded context block:

```text
Relevant continuity memory:
Directly relevant continuity memory:
1. [decision | role=direct | project=demo-dashboard | confidence=...]
   ...
```

The exact scores may change as retrieval tuning evolves, but the expected answer and selected synthetic record should remain stable.

## Try your own synthetic record

For experiments, copy the demo directory outside the repo or edit a temporary branch. Keep public fixtures synthetic and reviewable.

A minimal record looks like:

```json
{"id":"r_demo_decision","kind":"decision","scope_project":"demo-dashboard","title":"Demo dashboard API framework","summary":"The fictional demo-dashboard project should use FastAPI for its small Python API.","tags":["demo-dashboard","fastapi"],"entities":["FastAPI"],"confidence":0.86,"importance":0.7}
```

A matching query expectation looks like:

```json
{"query":"what API framework should demo-dashboard use?","scope_project":"demo-dashboard","must_include":["r_demo_decision"],"must_not_include":[],"top_k":3}
```

Then run:

```bash
./scripts/demo-retrieval.sh
```

## Why no real database is included

A real memory DB can contain personal preferences, project state, source references, accidental secrets, or stale facts. Public releases should ship auditable synthetic fixtures, not a real user memory database.

If you want to demo real memories privately, copy your database outside the repository and keep it out of git.
