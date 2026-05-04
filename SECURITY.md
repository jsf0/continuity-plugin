# Security Policy

## Supported versions

Hermes Continuity Memory is currently pre-1.0 alpha software. Security fixes are made on `main` until versioned releases are established.

## Reporting a vulnerability

If you find a vulnerability, please report it privately to the repository maintainer rather than opening a public issue. If no private GitHub security advisory channel is configured yet, contact the maintainer directly and include:

- affected version or commit;
- reproduction steps;
- impact;
- whether runtime memory data or credentials may be exposed;
- suggested mitigation, if known.

## Security model

Continuity is a local Hermes memory provider. It stores records in SQLite under:

```text
$HERMES_HOME/continuity/continuity.db
```

The plugin attempts to reduce risk by:

- redacting obvious secret patterns in observations and mirrored built-in memory writes;
- rejecting obvious prompt-injection-like text in conservative extraction and mirroring paths;
- bounding prompt injection with `max_records` and `max_chars`;
- labeling retrieved records as advisory background rather than instructions;
- exposing archive/delete lifecycle tools for cleanup.

## Non-goals / limitations

- This is not comprehensive DLP.
- This is not a multi-user access-control boundary.
- SQLite DB files are not encrypted by the plugin.
- Local neural embedding/reranking models may cache model artifacts outside this repository.
- Retrieved memories can still be stale, incomplete, or noisy; callers should verify important facts against source refs or live tools.

Do not store secrets, credentials, private keys, tokens, or regulated data in continuity memory.
