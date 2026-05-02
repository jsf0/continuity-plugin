"""Data models for continuity memory records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

ALLOWED_KINDS = frozenset(
    {
        "user_preference",
        "environment_fact",
        "project_convention",
        "lesson_learned",
        "decision",
        "session_summary",
        "artifact_summary",
        "procedure_candidate",
        "open_question",
        "active_project_state",
    }
)

ALLOWED_TRUST_LEVELS = frozenset(
    {
        "explicit_user",
        "built_in_memory_mirror",
        "agent_observed",
        "session_extracted",
        "tool_observed",
        "remote_untrusted",
    }
)


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SourceRef:
    """Reference to source material supporting a continuity memory record."""

    type: str
    id: str | None = None
    uri: str | None = None
    range: str | None = None
    label: str | None = None
    created_at: str | None = None

    def __post_init__(self) -> None:
        if not self.type.strip():
            raise ValueError("source type cannot be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "id": self.id,
            "uri": self.uri,
            "range": self.range,
            "label": self.label,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> SourceRef:
        return cls(
            type=str(value.get("type") or ""),
            id=_optional_str(value.get("id")),
            uri=_optional_str(value.get("uri")),
            range=_optional_str(value.get("range")),
            label=_optional_str(value.get("label")),
            created_at=_optional_str(value.get("created_at")),
        )


@dataclass(frozen=True)
class ContextRecord:
    """Structured continuity memory record."""

    id: str
    kind: str
    title: str
    summary: str
    scope_user: str | None = None
    scope_project: str | None = None
    scope_repo: str | None = None
    scope_profile: str | None = None
    details: str | None = None
    tags: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    confidence: float = 0.5
    importance: float = 0.5
    trust_level: str = "session_extracted"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    last_accessed_at: str | None = None
    last_confirmed_at: str | None = None
    expires_at: str | None = None
    source_hash: str | None = None
    embedding_text: str | None = None

    def __post_init__(self) -> None:
        _validate_non_empty("id", self.id)
        _validate_kind(self.kind)
        _validate_non_empty("title", self.title)
        _validate_non_empty("summary", self.summary)
        _validate_probability("confidence", self.confidence)
        _validate_probability("importance", self.importance)
        if self.trust_level not in ALLOWED_TRUST_LEVELS:
            raise ValueError(f"trust_level must be one of {sorted(ALLOWED_TRUST_LEVELS)}")

    @classmethod
    def new(
        cls,
        *,
        id: str,
        kind: str,
        title: str,
        summary: str,
        scope_user: str | None = None,
        scope_project: str | None = None,
        scope_repo: str | None = None,
        scope_profile: str | None = None,
        details: str | None = None,
        tags: list[str] | None = None,
        entities: list[str] | None = None,
        sources: list[SourceRef] | None = None,
        confidence: float = 0.5,
        importance: float = 0.5,
        trust_level: str = "session_extracted",
    ) -> ContextRecord:
        now = utc_now()
        normalized_tags = _normalize_string_list(tags)
        normalized_entities = _normalize_string_list(entities)
        record = cls(
            id=id,
            kind=kind,
            scope_user=scope_user,
            scope_project=scope_project,
            scope_repo=scope_repo,
            scope_profile=scope_profile,
            title=title,
            summary=summary,
            details=details,
            tags=normalized_tags,
            entities=normalized_entities,
            sources=list(sources or []),
            confidence=confidence,
            importance=importance,
            trust_level=trust_level,
            created_at=now,
            updated_at=now,
            embedding_text=None,
        )
        return record.with_embedding_text()

    def with_embedding_text(self) -> ContextRecord:
        text = " ".join(
            part
            for part in (
                self.kind,
                self.scope_project or "",
                self.title,
                self.summary,
                "tags:" + " ".join(self.tags) if self.tags else "",
                "entities:" + " ".join(self.entities) if self.entities else "",
            )
            if part
        )
        return _replace_record(self, embedding_text=text)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "scope_user": self.scope_user,
            "scope_project": self.scope_project,
            "scope_repo": self.scope_repo,
            "scope_profile": self.scope_profile,
            "title": self.title,
            "summary": self.summary,
            "details": self.details,
            "tags": list(self.tags),
            "entities": list(self.entities),
            "sources": [source.to_dict() for source in self.sources],
            "confidence": self.confidence,
            "importance": self.importance,
            "trust_level": self.trust_level,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_accessed_at": self.last_accessed_at,
            "last_confirmed_at": self.last_confirmed_at,
            "expires_at": self.expires_at,
            "source_hash": self.source_hash,
            "embedding_text": self.embedding_text,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> ContextRecord:
        record = cls(
            id=str(value.get("id") or ""),
            kind=str(value.get("kind") or ""),
            scope_user=_optional_str(value.get("scope_user")),
            scope_project=_optional_str(value.get("scope_project")),
            scope_repo=_optional_str(value.get("scope_repo")),
            scope_profile=_optional_str(value.get("scope_profile")),
            title=str(value.get("title") or ""),
            summary=str(value.get("summary") or ""),
            details=_optional_str(value.get("details")),
            tags=_normalize_string_list(value.get("tags")),
            entities=_normalize_string_list(value.get("entities")),
            sources=[SourceRef.from_dict(item) for item in _dict_list(value.get("sources"))],
            confidence=float(value.get("confidence", 0.5)),
            importance=float(value.get("importance", 0.5)),
            trust_level=str(value.get("trust_level") or "session_extracted"),
            created_at=str(value.get("created_at") or utc_now()),
            updated_at=str(value.get("updated_at") or utc_now()),
            last_accessed_at=_optional_str(value.get("last_accessed_at")),
            last_confirmed_at=_optional_str(value.get("last_confirmed_at")),
            expires_at=_optional_str(value.get("expires_at")),
            source_hash=_optional_str(value.get("source_hash")),
            embedding_text=_optional_str(value.get("embedding_text")),
        )
        return record if record.embedding_text else record.with_embedding_text()


def _replace_record(record: ContextRecord, **changes: object) -> ContextRecord:
    data = record.to_dict()
    data.update(changes)
    return ContextRecord.from_dict(data)


def _validate_non_empty(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _validate_kind(kind: str) -> None:
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"kind must be one of {sorted(ALLOWED_KINDS)}")


def _validate_probability(name: str, value: float) -> None:
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _normalize_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected a list of strings")
    return [str(item).strip() for item in value if str(item).strip()]


def _dict_list(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected a list of dictionaries")
    return [item for item in value if isinstance(item, dict)]
