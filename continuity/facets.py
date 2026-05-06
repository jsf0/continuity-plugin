"""Facet derivation shared by write-time quality checks and retrieval.

This module intentionally uses broad, public-safe facet tokens. It is not a
private/domain-specific ontology; it only derives coarse domains from literal
record text/metadata.
"""

from __future__ import annotations

import re

from .models import ContextRecord

GENERIC_PROJECT_SCOPES = frozenset({"", "root", "default", "global", "unknown"})

FACET_TOKEN_MAP: dict[str, frozenset[str]] = {
    "software_project": frozenset(
        {
            "api",
            "app",
            "build",
            "cargo",
            "ci",
            "cli",
            "code",
            "codebase",
            "config",
            "deployment",
            "dev",
            "git",
            "github",
            "lint",
            "programming",
            "pytest",
            "python",
            "repo",
            "repository",
            "ruff",
            "rust",
            "server",
            "service",
            "software",
            "test",
            "testing",
            "tool",
            "web",
        }
    ),
    "memory_system": frozenset(
        {
            "association",
            "continuity",
            "context",
            "dream",
            "embedding",
            "facet",
            "graph",
            "memory",
            "metadata",
            "prefetch",
            "rerank",
            "retrieval",
            "vector",
        }
    ),
    "personal_preference": frozenset(
        {"prefer", "preference", "user_preference", "style", "personal"}
    ),
    "personal_hardware": frozenset(
        {"desktop", "gpu", "hardware", "laptop", "machine", "pc", "workstation"}
    ),
    "vehicle_towing": frozenset(
        {"boat", "sailing", "tow", "towing", "trailer", "truck", "vehicle"}
    ),
    "devops_security": frozenset(
        {"auth", "certificate", "firewall", "proxy", "security", "ssl", "tls"}
    ),
}


def tokens_for_text(text: str) -> set[str]:
    """Return normalized lexical tokens used for coarse facet derivation."""

    tokens = {token.casefold() for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_:-]*", text)}
    expanded: set[str] = set()
    for token in tokens:
        expanded.add(token)
        expanded.add(token.replace("_", "-"))
        expanded.add(token.replace("-", "_"))
    return expanded


def facets_for_tokens(tokens: set[str]) -> set[str]:
    """Return coarse facets supported by the provided normalized tokens."""

    return {facet for facet, facet_tokens in FACET_TOKEN_MAP.items() if tokens & facet_tokens}


def facets_for_text(text: str) -> set[str]:
    """Derive coarse facets from literal text."""

    return facets_for_tokens(tokens_for_text(text))


def facets_for_record(record: ContextRecord) -> set[str]:
    """Derive coarse facets from a continuity record's write-time content."""

    text = " ".join(
        [
            record.kind,
            record.title,
            record.summary,
            record.details or "",
            record.scope_project or "",
            record.scope_repo or "",
            *record.tags,
            *record.entities,
        ]
    )
    facets = facets_for_text(text)
    if record.scope_project and record.scope_project not in GENERIC_PROJECT_SCOPES:
        facets |= facets_for_text(record.scope_project)
    if record.kind == "active_project_state":
        facets.add("software_project")
    if record.kind == "user_preference":
        facets.add("personal_preference")
    return facets
