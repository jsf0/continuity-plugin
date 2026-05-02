"""Tool schemas and handlers for the continuity memory provider."""

from __future__ import annotations

import uuid
from typing import Any

from .embeddings import VectorBackend
from .models import ContextRecord, SkillLink, SourceRef
from .retrieval import ContinuityRetriever, RetrievalHit
from .store import ContinuityStore

CONTINUITY_STATUS_SCHEMA: dict[str, object] = {
    "name": "continuity_status",
    "description": "Show status for the local continuity memory provider.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

CONTINUITY_SEARCH_SCHEMA: dict[str, object] = {
    "name": "continuity_search",
    "description": "Search local continuity memory records and return ranked results with scores.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for."},
            "limit": {"type": "integer", "description": "Maximum results to return."},
            "scope_project": {
                "type": "string",
                "description": "Optional project scope filter/boost.",
            },
        },
        "required": ["query"],
    },
}

CONTINUITY_GET_SCHEMA: dict[str, object] = {
    "name": "continuity_get",
    "description": "Fetch a continuity memory record by id.",
    "parameters": {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "Record id."}},
        "required": ["id"],
    },
}

CONTINUITY_ADD_SCHEMA: dict[str, object] = {
    "name": "continuity_add",
    "description": "Add or replace an explicit continuity memory record.",
    "parameters": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Optional stable record id."},
            "kind": {"type": "string", "description": "Record kind."},
            "title": {"type": "string", "description": "Short title."},
            "summary": {"type": "string", "description": "Compact memory summary."},
            "details": {"type": "string", "description": "Optional details."},
            "scope_project": {"type": "string", "description": "Optional project scope."},
            "scope_user": {"type": "string", "description": "Optional user scope."},
            "scope_repo": {"type": "string", "description": "Optional repo scope."},
            "scope_profile": {"type": "string", "description": "Optional profile scope."},
            "tags": {"type": "array", "items": {"type": "string"}},
            "entities": {"type": "array", "items": {"type": "string"}},
            "sources": {"type": "array", "items": {"type": "object"}},
            "confidence": {"type": "number"},
            "importance": {"type": "number"},
            "trust_level": {"type": "string"},
            "skill_links": {
                "type": "array",
                "description": "Optional links to relevant Hermes skills; skill bodies are not stored.",
                "items": {"type": "object"},
            },
        },
        "required": ["kind", "title", "summary"],
    },
}

CONTINUITY_DELETE_SCHEMA: dict[str, object] = {
    "name": "continuity_delete",
    "description": "Delete a continuity memory record by id.",
    "parameters": {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "Record id."}},
        "required": ["id"],
    },
}

ALL_TOOL_SCHEMAS = [
    CONTINUITY_STATUS_SCHEMA,
    CONTINUITY_SEARCH_SCHEMA,
    CONTINUITY_GET_SCHEMA,
    CONTINUITY_ADD_SCHEMA,
    CONTINUITY_DELETE_SCHEMA,
]


def handle_search(
    store: ContinuityStore,
    args: dict[str, Any],
    *,
    vector_backend: VectorBackend | None = None,
) -> dict[str, object]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"success": False, "error": "query is required for continuity_search"}
    limit = _bounded_int(args.get("limit"), default=5, minimum=1, maximum=20)
    scope_project = _optional_str(args.get("scope_project"))
    hits = ContinuityRetriever(store, vector_backend=vector_backend).search(
        query,
        scope_project=scope_project,
        limit=limit,
    )
    return {
        "success": True,
        "query": query,
        "results": [_hit_to_dict(hit) for hit in hits],
    }


def handle_get(store: ContinuityStore, args: dict[str, Any]) -> dict[str, object]:
    record_id = str(args.get("id") or "").strip()
    if not record_id:
        return {"success": False, "error": "id is required for continuity_get"}
    record = store.get_record(record_id)
    if record is None:
        return {"success": False, "error": f"record not found: {record_id}"}
    return {
        "success": True,
        "record": record.to_dict(),
        "skill_links": [link.to_dict() for link in store.list_skill_links(record.id)],
    }


def handle_add(store: ContinuityStore, args: dict[str, Any]) -> dict[str, object]:
    missing = [
        name for name in ("kind", "title", "summary") if not str(args.get(name) or "").strip()
    ]
    if missing:
        return {"success": False, "error": f"missing required field(s): {', '.join(missing)}"}
    try:
        record = ContextRecord.new(
            id=str(args.get("id") or f"r_{uuid.uuid4().hex}"),
            kind=str(args["kind"]),
            title=str(args["title"]),
            summary=str(args["summary"]),
            scope_user=_optional_str(args.get("scope_user")),
            scope_project=_optional_str(args.get("scope_project")),
            scope_repo=_optional_str(args.get("scope_repo")),
            scope_profile=_optional_str(args.get("scope_profile")),
            details=_optional_str(args.get("details")),
            tags=_string_list(args.get("tags")),
            entities=_string_list(args.get("entities")),
            sources=[SourceRef.from_dict(item) for item in _dict_list(args.get("sources"))],
            confidence=_bounded_float(args.get("confidence"), default=0.5),
            importance=_bounded_float(args.get("importance"), default=0.5),
            trust_level=str(args.get("trust_level") or "explicit_user"),
        )
    except (TypeError, ValueError) as exc:
        return {"success": False, "error": str(exc)}
    try:
        skill_links = _skill_links(record.id, args.get("skill_links"))
    except (TypeError, ValueError) as exc:
        return {"success": False, "error": str(exc)}
    store.upsert_record(record)
    store.replace_skill_links(record.id, skill_links)
    return {
        "success": True,
        "record": record.to_dict(),
        "skill_links": [link.to_dict() for link in skill_links],
    }


def handle_delete(store: ContinuityStore, args: dict[str, Any]) -> dict[str, object]:
    record_id = str(args.get("id") or "").strip()
    if not record_id:
        return {"success": False, "error": "id is required for continuity_delete"}
    existed = store.get_record(record_id) is not None
    store.delete_record(record_id)
    return {"success": True, "deleted": existed, "id": record_id}


def _hit_to_dict(hit: RetrievalHit) -> dict[str, object]:
    record = hit.record
    return {
        "id": record.id,
        "kind": record.kind,
        "title": record.title,
        "summary": record.summary,
        "scope_project": record.scope_project,
        "score": hit.score,
        "reasons": list(hit.reasons),
        "sources": [source.to_dict() for source in record.sources],
        "skill_links": [link.to_dict() for link in hit.skill_links],
    }


def _skill_links(record_id: str, value: object) -> list[SkillLink]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected list of skill link objects")
    links: list[SkillLink] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("expected list of skill link objects")
        data = dict(item)
        data["record_id"] = record_id
        links.append(SkillLink.from_dict(data))
    return links


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(maximum, max(minimum, parsed))


def _bounded_float(value: object, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return min(1.0, max(0.0, parsed))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected list of strings")
    return [str(item).strip() for item in value if str(item).strip()]


def _dict_list(value: object) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected list of objects")
    return [item for item in value if isinstance(item, dict)]
