"""Conservative session extraction for continuity memory."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from continuity.models import ContextRecord, SourceRef
from continuity.security import is_safe_memory_text

_PREFIX_PATTERNS = [
    (re.compile(r"\bremember\s*:\s*(.+)", re.IGNORECASE), "user_preference"),
    (re.compile(r"\blesson learned\s*:\s*(.+)", re.IGNORECASE), "lesson_learned"),
    (re.compile(r"\bdecision\s*:\s*(.+)", re.IGNORECASE), "decision"),
]


def extract_records_from_messages(
    *,
    session_id: str,
    messages: Iterable[dict[str, object]],
    scope_project: str | None = None,
) -> list[ContextRecord]:
    """Extract conservative structured records from session messages.

    This Phase 5 extractor is intentionally heuristic. It only extracts clear
    durable-memory markers and rejects unsafe text.
    """
    records: list[ContextRecord] = []
    seen_ids: set[str] = set()
    for index, message in enumerate(messages, start=1):
        content = str(message.get("content") or "").strip()
        if len(content) < 12 or not is_safe_memory_text(content):
            continue
        for pattern, kind in _PREFIX_PATTERNS:
            match = pattern.search(content)
            if not match:
                continue
            summary = _clean_summary(match.group(1))
            if not summary or not is_safe_memory_text(summary):
                continue
            if kind == "user_preference" and "prefer" not in summary.lower():
                # Avoid turning arbitrary "remember" notes into durable facts in Phase 5.
                continue
            record_id = _record_id(kind, summary, scope_project)
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)
            records.append(
                ContextRecord.new(
                    id=record_id,
                    kind=kind,
                    title=_title_for(kind, summary),
                    summary=summary,
                    scope_project=scope_project,
                    tags=_tags_for(kind, summary),
                    entities=_entities_for(summary),
                    sources=[SourceRef(type="session", id=session_id, range=f"turn {index}")],
                    confidence=0.8,
                    importance=0.75,
                    trust_level="session_extracted",
                )
            )
            break
    return records


def _clean_summary(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(".") + "."


def _record_id(kind: str, summary: str, scope_project: str | None) -> str:
    digest = hashlib.sha256(
        f"{kind}\0{scope_project or ''}\0{summary.lower()}".encode()
    ).hexdigest()
    return f"r_{kind}_{digest[:16]}"


def _title_for(kind: str, summary: str) -> str:
    words = summary.split()
    return f"{kind.replace('_', ' ')}: {' '.join(words[:8]).rstrip('.')}"


def _tags_for(kind: str, summary: str) -> list[str]:
    tags = [kind]
    lower = summary.lower()
    for token in ("delegate_task", "timeout", "api_calls:0", "foundation-first", "auth"):
        if token in lower:
            tags.append(token)
    return tags


def _entities_for(summary: str) -> list[str]:
    entities: list[str] = []
    for token in re.findall(r"[A-Za-z_][\w:-]{2,}", summary):
        if any(marker in token for marker in ("_", ":", "-")):
            entities.append(token)
    return entities
