"""Security helpers for continuity memory storage and extraction."""

from __future__ import annotations

import re

_THREAT_PATTERNS = [
    re.compile(r"ignore\s+(previous|all|above|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt\s+override", re.IGNORECASE),
    re.compile(r"do\s+not\s+tell\s+the\s+user", re.IGNORECASE),
    re.compile(r"reveal\s+secrets?", re.IGNORECASE),
]

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{10,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s]+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
]


def is_safe_memory_text(text: str) -> bool:
    """Return False when text contains obvious prompt-injection or secret content."""
    return not any(pattern.search(text) for pattern in [*_THREAT_PATTERNS, *_SECRET_PATTERNS])


def redact_sensitive_text(text: str) -> str:
    """Redact obvious secrets while preserving surrounding context."""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


def truncate_text(text: str, *, max_chars: int) -> str:
    """Truncate text to a hard character budget."""
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1].rstrip() + "…"


def sanitize_observation_text(text: str, *, max_chars: int) -> str:
    """Redact and truncate text before writing turn observations."""
    return truncate_text(redact_sensitive_text(text), max_chars=max_chars)
