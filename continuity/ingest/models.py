"""Core data models for corpus ingestion."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

JsonObject = dict[str, Any]


def stable_hash(value: object) -> str:
    """Return a deterministic SHA-256 hash for a JSON-serializable value."""

    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_id(*parts: object, prefix: str = "ing") -> str:
    """Return a deterministic ingestion id from one or more parts."""

    return f"{prefix}_{stable_hash([str(part) for part in parts])[:24]}"


def _validate_non_empty(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _validate_probability(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError("expected a list")
    return [str(item) for item in value]


def _dict(value: object) -> JsonObject:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError("expected a dict")
    return dict(value)


@dataclass(frozen=True)
class SourceLocation:
    """Location of parsed or segmented content inside a source."""

    uri: str | None = None
    path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    page_start: int | None = None
    page_end: int | None = None

    def __post_init__(self) -> None:
        for name in ("line_start", "line_end", "page_start", "page_end"):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValueError(f"{name} must be positive")
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_end < self.line_start
        ):
            raise ValueError("line_end cannot be before line_start")
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end cannot be before page_start")

    def to_dict(self) -> JsonObject:
        return {
            "uri": self.uri,
            "path": self.path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "page_start": self.page_start,
            "page_end": self.page_end,
        }

    @classmethod
    def from_dict(cls, value: JsonObject) -> SourceLocation:
        return cls(
            uri=_optional_str(value.get("uri")),
            path=_optional_str(value.get("path")),
            line_start=_optional_int(value.get("line_start")),
            line_end=_optional_int(value.get("line_end")),
            page_start=_optional_int(value.get("page_start")),
            page_end=_optional_int(value.get("page_end")),
        )


@dataclass(frozen=True)
class SourceRef:
    """Reference to source material supporting a candidate memory."""

    type: str
    uri: str | None = None
    path: str | None = None
    segment_id: str | None = None
    section: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    title: str | None = None
    url: str | None = None
    content_hash: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_non_empty("type", self.type)
        for name in ("line_start", "line_end", "page_start", "page_end"):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValueError(f"{name} must be positive")
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_end < self.line_start
        ):
            raise ValueError("line_end cannot be before line_start")
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end cannot be before page_start")

    def to_dict(self) -> JsonObject:
        return {
            "type": self.type,
            "uri": self.uri,
            "path": self.path,
            "segment_id": self.segment_id,
            "section": self.section,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "title": self.title,
            "url": self.url,
            "content_hash": self.content_hash,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, value: JsonObject) -> SourceRef:
        return cls(
            type=str(value.get("type") or ""),
            uri=_optional_str(value.get("uri")),
            path=_optional_str(value.get("path")),
            segment_id=_optional_str(value.get("segment_id")),
            section=_optional_str(value.get("section")),
            line_start=_optional_int(value.get("line_start")),
            line_end=_optional_int(value.get("line_end")),
            page_start=_optional_int(value.get("page_start")),
            page_end=_optional_int(value.get("page_end")),
            title=_optional_str(value.get("title")),
            url=_optional_str(value.get("url")),
            content_hash=_optional_str(value.get("content_hash")),
            metadata=_dict(value.get("metadata")),
        )


@dataclass(frozen=True)
class SourceDocument:
    """A discovered corpus artifact before parsing."""

    source_id: str
    source_type: str
    uri: str
    title: str | None = None
    collection: str | None = None
    metadata: JsonObject = field(default_factory=dict)
    scope_project: str | None = None
    scope_repo: str | None = None
    scope_user: str | None = None
    scope_profile: str | None = None

    def __post_init__(self) -> None:
        _validate_non_empty("source_id", self.source_id)
        _validate_non_empty("source_type", self.source_type)
        _validate_non_empty("uri", self.uri)

    def to_dict(self) -> JsonObject:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "uri": self.uri,
            "title": self.title,
            "collection": self.collection,
            "metadata": self.metadata,
            "scope_project": self.scope_project,
            "scope_repo": self.scope_repo,
            "scope_user": self.scope_user,
            "scope_profile": self.scope_profile,
        }

    @classmethod
    def from_dict(cls, value: JsonObject) -> SourceDocument:
        return cls(
            source_id=str(value.get("source_id") or ""),
            source_type=str(value.get("source_type") or ""),
            uri=str(value.get("uri") or ""),
            title=_optional_str(value.get("title")),
            collection=_optional_str(value.get("collection")),
            metadata=_dict(value.get("metadata")),
            scope_project=_optional_str(value.get("scope_project")),
            scope_repo=_optional_str(value.get("scope_repo")),
            scope_user=_optional_str(value.get("scope_user")),
            scope_profile=_optional_str(value.get("scope_profile")),
        )


@dataclass(frozen=True)
class ParsedBlock:
    """Structured block emitted by a parser."""

    block_id: str
    kind: str
    text: str
    level: int | None = None
    location: SourceLocation | None = None
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_non_empty("block_id", self.block_id)
        _validate_non_empty("kind", self.kind)
        if self.level is not None and self.level < 1:
            raise ValueError("level must be positive")

    def to_dict(self) -> JsonObject:
        return {
            "block_id": self.block_id,
            "kind": self.kind,
            "text": self.text,
            "level": self.level,
            "location": self.location.to_dict() if self.location else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, value: JsonObject) -> ParsedBlock:
        location = value.get("location")
        return cls(
            block_id=str(value.get("block_id") or ""),
            kind=str(value.get("kind") or ""),
            text=str(value.get("text") or ""),
            level=_optional_int(value.get("level")),
            location=SourceLocation.from_dict(location) if isinstance(location, dict) else None,
            metadata=_dict(value.get("metadata")),
        )


@dataclass(frozen=True)
class ParsedDocument:
    """A parsed document with text and structural blocks."""

    source_id: str
    source_type: str
    title: str | None = None
    text: str | None = None
    blocks: list[ParsedBlock] = field(default_factory=list)
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_non_empty("source_id", self.source_id)
        _validate_non_empty("source_type", self.source_type)

    def to_dict(self) -> JsonObject:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "title": self.title,
            "text": self.text,
            "blocks": [block.to_dict() for block in self.blocks],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, value: JsonObject) -> ParsedDocument:
        blocks = value.get("blocks") or []
        if not isinstance(blocks, list):
            raise TypeError("blocks must be a list")
        return cls(
            source_id=str(value.get("source_id") or ""),
            source_type=str(value.get("source_type") or ""),
            title=_optional_str(value.get("title")),
            text=_optional_str(value.get("text")),
            blocks=[ParsedBlock.from_dict(block) for block in blocks if isinstance(block, dict)],
            metadata=_dict(value.get("metadata")),
        )


@dataclass(frozen=True)
class SourceSegment:
    """A meaningful source unit for candidate extraction."""

    segment_id: str
    source_id: str
    kind: str
    title: str | None
    text: str
    location: SourceLocation | None = None
    metadata: JsonObject = field(default_factory=dict)
    scope_project: str | None = None
    scope_repo: str | None = None
    scope_user: str | None = None
    scope_profile: str | None = None

    def __post_init__(self) -> None:
        _validate_non_empty("segment_id", self.segment_id)
        _validate_non_empty("source_id", self.source_id)
        _validate_non_empty("kind", self.kind)

    def to_dict(self) -> JsonObject:
        return {
            "segment_id": self.segment_id,
            "source_id": self.source_id,
            "kind": self.kind,
            "title": self.title,
            "text": self.text,
            "location": self.location.to_dict() if self.location else None,
            "metadata": self.metadata,
            "scope_project": self.scope_project,
            "scope_repo": self.scope_repo,
            "scope_user": self.scope_user,
            "scope_profile": self.scope_profile,
        }

    @classmethod
    def from_dict(cls, value: JsonObject) -> SourceSegment:
        location = value.get("location")
        return cls(
            segment_id=str(value.get("segment_id") or ""),
            source_id=str(value.get("source_id") or ""),
            kind=str(value.get("kind") or ""),
            title=_optional_str(value.get("title")),
            text=str(value.get("text") or ""),
            location=SourceLocation.from_dict(location) if isinstance(location, dict) else None,
            metadata=_dict(value.get("metadata")),
            scope_project=_optional_str(value.get("scope_project")),
            scope_repo=_optional_str(value.get("scope_repo")),
            scope_user=_optional_str(value.get("scope_user")),
            scope_profile=_optional_str(value.get("scope_profile")),
        )


@dataclass(frozen=True)
class CandidateRecord:
    """A proposed continuity memory record before import."""

    candidate_id: str
    kind: str
    title: str
    summary: str
    details: str | None = None
    scope_project: str | None = None
    scope_repo: str | None = None
    scope_user: str | None = None
    scope_profile: str | None = None
    tags: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    confidence: float = 0.5
    importance: float = 0.5
    trust_level: str = "corpus_distilled"
    source_refs: list[SourceRef] = field(default_factory=list)
    ingestion: JsonObject = field(default_factory=dict)
    review: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_non_empty("candidate_id", self.candidate_id)
        _validate_non_empty("kind", self.kind)
        _validate_non_empty("title", self.title)
        _validate_non_empty("summary", self.summary)
        _validate_probability("confidence", self.confidence)
        _validate_probability("importance", self.importance)
        if self.trust_level.startswith("corpus") and not self.source_refs:
            raise ValueError("source_refs are required for corpus-derived candidate records")

    def to_dict(self) -> JsonObject:
        return {
            "candidate_id": self.candidate_id,
            "kind": self.kind,
            "title": self.title,
            "summary": self.summary,
            "details": self.details,
            "scope_project": self.scope_project,
            "scope_repo": self.scope_repo,
            "scope_user": self.scope_user,
            "scope_profile": self.scope_profile,
            "tags": self.tags,
            "entities": self.entities,
            "confidence": self.confidence,
            "importance": self.importance,
            "trust_level": self.trust_level,
            "source_refs": [source_ref.to_dict() for source_ref in self.source_refs],
            "ingestion": self.ingestion,
            "review": self.review,
        }

    @classmethod
    def from_dict(cls, value: JsonObject) -> CandidateRecord:
        source_refs = value.get("source_refs") or []
        if not isinstance(source_refs, list):
            raise TypeError("source_refs must be a list")
        return cls(
            candidate_id=str(value.get("candidate_id") or ""),
            kind=str(value.get("kind") or ""),
            title=str(value.get("title") or ""),
            summary=str(value.get("summary") or ""),
            details=_optional_str(value.get("details")),
            scope_project=_optional_str(value.get("scope_project")),
            scope_repo=_optional_str(value.get("scope_repo")),
            scope_user=_optional_str(value.get("scope_user")),
            scope_profile=_optional_str(value.get("scope_profile")),
            tags=_string_list(value.get("tags")),
            entities=_string_list(value.get("entities")),
            confidence=float(value.get("confidence", 0.5)),
            importance=float(value.get("importance", 0.5)),
            trust_level=str(value.get("trust_level") or "corpus_distilled"),
            source_refs=[SourceRef.from_dict(ref) for ref in source_refs if isinstance(ref, dict)],
            ingestion=_dict(value.get("ingestion")),
            review=_dict(value.get("review")),
        )


@dataclass(frozen=True)
class IngestionRunManifest:
    """Summary manifest for one ingestion run."""

    run_id: str
    created_at: str
    recipe: str
    input_roots: list[str]
    config_hash: str
    source_count: int = 0
    segment_count: int = 0
    candidate_count: int = 0
    approved_count: int = 0
    imported_count: int = 0
    rejected_count: int = 0
    output_dir: str | None = None

    def __post_init__(self) -> None:
        _validate_non_empty("run_id", self.run_id)
        _validate_non_empty("created_at", self.created_at)
        _validate_non_empty("recipe", self.recipe)
        _validate_non_empty("config_hash", self.config_hash)
        for name in (
            "source_count",
            "segment_count",
            "candidate_count",
            "approved_count",
            "imported_count",
            "rejected_count",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")

    def to_dict(self) -> JsonObject:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "recipe": self.recipe,
            "input_roots": self.input_roots,
            "config_hash": self.config_hash,
            "source_count": self.source_count,
            "segment_count": self.segment_count,
            "candidate_count": self.candidate_count,
            "approved_count": self.approved_count,
            "imported_count": self.imported_count,
            "rejected_count": self.rejected_count,
            "output_dir": self.output_dir,
        }

    @classmethod
    def from_dict(cls, value: JsonObject) -> IngestionRunManifest:
        return cls(
            run_id=str(value.get("run_id") or ""),
            created_at=str(value.get("created_at") or ""),
            recipe=str(value.get("recipe") or ""),
            input_roots=_string_list(value.get("input_roots")),
            config_hash=str(value.get("config_hash") or ""),
            source_count=int(value.get("source_count", 0)),
            segment_count=int(value.get("segment_count", 0)),
            candidate_count=int(value.get("candidate_count", 0)),
            approved_count=int(value.get("approved_count", 0)),
            imported_count=int(value.get("imported_count", 0)),
            rejected_count=int(value.get("rejected_count", 0)),
            output_dir=_optional_str(value.get("output_dir")),
        )


@dataclass(frozen=True)
class Rejection:
    """A rejected source, segment, or candidate with reasons."""

    item_id: str
    item_type: str
    reasons: list[str]
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_non_empty("item_id", self.item_id)
        _validate_non_empty("item_type", self.item_type)
        if not self.reasons:
            raise ValueError("reasons cannot be empty")

    def to_dict(self) -> JsonObject:
        return {
            "item_id": self.item_id,
            "item_type": self.item_type,
            "reasons": self.reasons,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, value: JsonObject) -> Rejection:
        return cls(
            item_id=str(value.get("item_id") or ""),
            item_type=str(value.get("item_type") or ""),
            reasons=_string_list(value.get("reasons")),
            metadata=_dict(value.get("metadata")),
        )


@dataclass(frozen=True)
class ReviewDecision:
    """Review decision for a candidate record."""

    candidate_id: str
    status: str
    reasons: list[str] = field(default_factory=list)
    reviewer: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_non_empty("candidate_id", self.candidate_id)
        _validate_non_empty("status", self.status)

    def to_dict(self) -> JsonObject:
        return {
            "candidate_id": self.candidate_id,
            "status": self.status,
            "reasons": self.reasons,
            "reviewer": self.reviewer,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, value: JsonObject) -> ReviewDecision:
        return cls(
            candidate_id=str(value.get("candidate_id") or ""),
            status=str(value.get("status") or ""),
            reasons=_string_list(value.get("reasons")),
            reviewer=_optional_str(value.get("reviewer")),
            metadata=_dict(value.get("metadata")),
        )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)
