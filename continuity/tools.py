"""Tool schemas and handlers for the continuity memory provider."""

from __future__ import annotations

import uuid
from typing import Any

from .config import DreamConfig, RetrievalGateConfig
from .dream import run_dream_cycle
from .embeddings import VectorBackend
from .models import ContextRecord, SkillLink, SourceRef
from .quality_backfill import apply_quality_backfill, build_quality_backfill_report
from .record_quality import enrich_record_metadata
from .reranking import RerankerBackend
from .retrieval import (
    ContinuityRetriever,
    RetrievalHit,
    candidate_to_debug_dict,
    tuning_advice_for_reason,
)
from .staleness import find_stale_candidates
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
            "include_stale": {
                "type": "boolean",
                "description": "Include archived, retracted, and expired records for inspection.",
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
            "scope_project": {
                "type": "string",
                "description": "Optional project scope.",
            },
            "scope_user": {"type": "string", "description": "Optional user scope."},
            "scope_repo": {"type": "string", "description": "Optional repo scope."},
            "scope_profile": {
                "type": "string",
                "description": "Optional profile scope.",
            },
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

CONTINUITY_ARCHIVE_SCHEMA: dict[str, object] = {
    "name": "continuity_archive",
    "description": "Archive a stale continuity memory record so retrieval excludes it by default.",
    "parameters": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Record id."},
            "reason": {"type": "string", "description": "Reason for archiving."},
            "superseded_by": {
                "type": "string",
                "description": "Optional replacement record id.",
            },
        },
        "required": ["id"],
    },
}

CONTINUITY_RESTORE_SCHEMA: dict[str, object] = {
    "name": "continuity_restore",
    "description": "Restore an archived or retracted continuity memory record to active retrieval.",
    "parameters": {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "Record id."}},
        "required": ["id"],
    },
}

CONTINUITY_PRUNE_STALE_SCHEMA: dict[str, object] = {
    "name": "continuity_prune_stale",
    "description": "Find and optionally archive/delete deterministic stale memory candidates. Dry-run by default.",
    "parameters": {
        "type": "object",
        "properties": {
            "dry_run": {
                "type": "boolean",
                "description": "Only report candidates; default true.",
            },
            "mode": {
                "type": "string",
                "description": "archive or delete; default archive.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum candidates to inspect.",
            },
        },
        "required": [],
    },
}

CONTINUITY_DEBUG_RETRIEVAL_SCHEMA: dict[str, object] = {
    "name": "continuity_debug_retrieval",
    "description": "Explain continuity retrieval candidates, scores, and rejection reasons for a query.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to debug."},
            "limit": {
                "type": "integer",
                "description": "Maximum selected results to return.",
            },
            "scope_project": {
                "type": "string",
                "description": "Optional project scope.",
            },
            "include_stale": {
                "type": "boolean",
                "description": "Include stale records.",
            },
        },
        "required": ["query"],
    },
}

CONTINUITY_ASSOCIATION_EDGES_SCHEMA: dict[str, object] = {
    "name": "continuity_association_edges",
    "description": "List continuity memory association graph edges for debugging noisy retrieval.",
    "parameters": {
        "type": "object",
        "properties": {
            "record_id": {
                "type": "string",
                "description": "Optional record id to inspect adjacent edges only.",
            },
            "limit": {"type": "integer", "description": "Maximum edges to return."},
        },
        "required": [],
    },
}

CONTINUITY_REINDEX_VECTORS_SCHEMA: dict[str, object] = {
    "name": "continuity_reindex_vectors",
    "description": "Rebuild vector embeddings for active continuity records.",
    "parameters": {
        "type": "object",
        "properties": {
            "include_stale": {
                "type": "boolean",
                "description": "Index stale records too.",
            },
        },
        "required": [],
    },
}

CONTINUITY_DREAM_SCHEMA: dict[str, object] = {
    "name": "continuity_dream",
    "description": "Run an offline continuity memory dream cycle: report stale candidates or safely archive them.",
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "description": "report, archive-safe, or archive-all-candidates. Defaults to configured dream mode.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum stale candidates to inspect/archive.",
            },
        },
        "required": [],
    },
}

CONTINUITY_QUALITY_REPORT_SCHEMA: dict[str, object] = {
    "name": "continuity_quality_report",
    "description": (
        "Report persisted write-time quality warnings, or recompute/apply "
        "conservative quality_json-only backfill when requested."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum warning/drift records to return.",
            },
            "recompute": {
                "type": "boolean",
                "description": "If true, recompute quality for existing records and report drift.",
            },
            "apply_backfill": {
                "type": "boolean",
                "description": (
                    "When recompute is true, persist recomputed quality_json only; "
                    "retrieval content and metadata are left untouched."
                ),
            },
            "active_only": {
                "type": "boolean",
                "description": "If true in recompute mode, inspect only active records.",
            },
        },
        "required": [],
    },
}

ALL_TOOL_SCHEMAS = [
    CONTINUITY_STATUS_SCHEMA,
    CONTINUITY_SEARCH_SCHEMA,
    CONTINUITY_GET_SCHEMA,
    CONTINUITY_ADD_SCHEMA,
    CONTINUITY_DELETE_SCHEMA,
    CONTINUITY_ARCHIVE_SCHEMA,
    CONTINUITY_RESTORE_SCHEMA,
    CONTINUITY_PRUNE_STALE_SCHEMA,
    CONTINUITY_DEBUG_RETRIEVAL_SCHEMA,
    CONTINUITY_ASSOCIATION_EDGES_SCHEMA,
    CONTINUITY_REINDEX_VECTORS_SCHEMA,
    CONTINUITY_DREAM_SCHEMA,
    CONTINUITY_QUALITY_REPORT_SCHEMA,
]


def handle_search(
    store: ContinuityStore,
    args: dict[str, Any],
    *,
    vector_backend: VectorBackend | None = None,
    reranker_backend: RerankerBackend | None = None,
    reranker_min_score: float = 0.15,
    reranker_weight: float = 2.0,
    reranker_top_k: int = 20,
    association_enabled: bool = True,
    association_edge_creation_threshold: float = 0.25,
    association_out_degree_cap: int = 20,
    association_hop_decay: float = 0.6,
    association_activation_threshold: float = 0.3,
    association_max_hops: int = 2,
    gate_config: RetrievalGateConfig | None = None,
) -> dict[str, object]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"success": False, "error": "query is required for continuity_search"}
    limit = _bounded_int(args.get("limit"), default=5, minimum=1, maximum=20)
    scope_project = _optional_str(args.get("scope_project"))
    include_stale = _bool(args.get("include_stale"), False)
    hits = ContinuityRetriever(
        store,
        vector_backend=vector_backend,
        reranker_backend=reranker_backend,
        reranker_min_score=reranker_min_score,
        reranker_weight=reranker_weight,
        reranker_top_k=reranker_top_k,
        association_enabled=association_enabled,
        association_edge_creation_threshold=association_edge_creation_threshold,
        association_out_degree_cap=association_out_degree_cap,
        association_hop_decay=association_hop_decay,
        association_activation_threshold=association_activation_threshold,
        association_max_hops=association_max_hops,
        gate_config=gate_config,
    ).search(
        query,
        scope_project=scope_project,
        limit=limit,
        include_stale=include_stale,
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
        return {
            "success": False,
            "error": f"missing required field(s): {', '.join(missing)}",
        }
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
        record, _assessment = enrich_record_metadata(record)
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


def handle_debug_retrieval(
    store: ContinuityStore,
    args: dict[str, Any],
    *,
    vector_backend: VectorBackend | None = None,
    reranker_backend: RerankerBackend | None = None,
    reranker_min_score: float = 0.15,
    reranker_weight: float = 2.0,
    reranker_top_k: int = 20,
    association_enabled: bool = True,
    association_edge_creation_threshold: float = 0.25,
    association_out_degree_cap: int = 20,
    association_hop_decay: float = 0.6,
    association_activation_threshold: float = 0.3,
    association_max_hops: int = 2,
    gate_config: RetrievalGateConfig | None = None,
) -> dict[str, object]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {
            "success": False,
            "error": "query is required for continuity_debug_retrieval",
        }
    limit = _bounded_int(args.get("limit"), default=5, minimum=1, maximum=20)
    debug = ContinuityRetriever(
        store,
        vector_backend=vector_backend,
        reranker_backend=reranker_backend,
        reranker_min_score=reranker_min_score,
        reranker_weight=reranker_weight,
        reranker_top_k=reranker_top_k,
        association_enabled=association_enabled,
        association_edge_creation_threshold=association_edge_creation_threshold,
        association_out_degree_cap=association_out_degree_cap,
        association_hop_decay=association_hop_decay,
        association_activation_threshold=association_activation_threshold,
        association_max_hops=association_max_hops,
        gate_config=gate_config,
    ).debug_search(
        query,
        scope_project=_optional_str(args.get("scope_project")),
        limit=limit,
        include_stale=_bool(args.get("include_stale"), False),
    )
    rejected_items = [candidate_to_debug_dict(item) for item in debug["rejected"]]
    activation_trace = debug.get("activation_trace", {})
    return {
        "success": True,
        "query": query,
        "tokens": debug["tokens"],
        "expanded_tokens": debug["expanded_tokens"],
        "selected": [candidate_to_debug_dict(item) for item in debug["selected"]],
        "rejected": rejected_items,
        "activation_trace": activation_trace,
        "tuning_advice": _collect_tuning_advice(rejected_items, activation_trace),
    }


def _collect_tuning_advice(
    rejected_items: list[dict[str, object]], activation_trace: object
) -> list[dict[str, str]]:
    seen: set[str] = set()
    advice: list[dict[str, str]] = []

    def add_reason(reason: object) -> None:
        if not isinstance(reason, str) or reason in seen:
            return
        item = tuning_advice_for_reason(reason)
        if item is None:
            return
        seen.add(reason)
        advice.append(item)

    for item in rejected_items:
        add_reason(item.get("rejected_reason"))
    if isinstance(activation_trace, dict):
        for item in activation_trace.get("cut_neighbors", []):
            if isinstance(item, dict):
                add_reason(item.get("reason"))
    return advice


def handle_quality_report(store: ContinuityStore, args: dict[str, Any]) -> dict[str, object]:
    limit = _bounded_int(args.get("limit"), default=100, minimum=1, maximum=500)
    recompute = _bool(args.get("recompute"), False)
    if recompute:
        active_only = _bool(args.get("active_only"), False)
        apply_backfill_requested = _bool(args.get("apply_backfill"), False)
        report = (
            apply_quality_backfill(store, limit=limit, active_only=active_only)
            if apply_backfill_requested
            else build_quality_backfill_report(store, limit=limit, active_only=active_only)
        )
        return {
            "success": True,
            "mode": "recompute",
            "applied": apply_backfill_requested,
            "updated_count": report.updated_count,
            "records": report.records,
            "top_warnings": report.top_warnings,
            "counts": {
                "record_count": report.record_count,
                "warning_records": report.warning_count,
                "review_required": report.review_required_count,
                "drift_records": report.drift_count,
            },
        }

    records = store.list_quality_inventory(limit=limit)
    return {
        "success": True,
        "mode": "persisted",
        "applied": False,
        "updated_count": 0,
        "records": records,
        "counts": {
            "warning_records": len(records),
            "review_required": sum(1 for item in records if item.get("review_required")),
        },
    }


def handle_association_edges(store: ContinuityStore, args: dict[str, Any]) -> dict[str, object]:
    limit = _bounded_int(args.get("limit"), default=50, minimum=1, maximum=500)
    record_id = _optional_str(args.get("record_id"))
    return {
        "success": True,
        "record_id": record_id,
        "edges": store.list_association_edge_inventory(record_id=record_id, limit=limit),
    }


def handle_reindex_vectors(
    store: ContinuityStore,
    args: dict[str, Any],
    *,
    vector_backend: VectorBackend | None = None,
    backend_name: str = "none",
    model: str | None = None,
) -> dict[str, object]:
    if vector_backend is None:
        return {"success": False, "error": "vector backend is not configured"}
    if not vector_backend.is_available():
        return {"success": False, "error": "vector backend is not available"}
    include_stale = _bool(args.get("include_stale"), False)
    indexed = 0
    skipped = 0
    for record in store.list_records():
        if not include_stale and record.status != "active":
            skipped += 1
            continue
        vector_backend.upsert(
            record.id,
            record.with_embedding_text().embedding_text or record.embedding_text or "",
        )
        indexed += 1
    return {
        "success": True,
        "indexed": indexed,
        "skipped": skipped,
        "backend": backend_name,
        "model": model,
    }


def handle_delete(store: ContinuityStore, args: dict[str, Any]) -> dict[str, object]:
    record_id = str(args.get("id") or "").strip()
    if not record_id:
        return {"success": False, "error": "id is required for continuity_delete"}
    existed = store.get_record(record_id) is not None
    store.delete_record(record_id)
    return {"success": True, "deleted": existed, "id": record_id}


def handle_archive(store: ContinuityStore, args: dict[str, Any]) -> dict[str, object]:
    record_id = str(args.get("id") or "").strip()
    if not record_id:
        return {"success": False, "error": "id is required for continuity_archive"}
    archived = store.archive_record(
        record_id,
        reason=_optional_str(args.get("reason")),
        superseded_by=_optional_str(args.get("superseded_by")),
    )
    return {"success": True, "archived": archived, "id": record_id}


def handle_restore(store: ContinuityStore, args: dict[str, Any]) -> dict[str, object]:
    record_id = str(args.get("id") or "").strip()
    if not record_id:
        return {"success": False, "error": "id is required for continuity_restore"}
    restored = store.restore_record(record_id)
    return {"success": True, "restored": restored, "id": record_id}


def handle_dream(
    store: ContinuityStore,
    args: dict[str, Any],
    *,
    config: DreamConfig,
    stale_after_days: int = 180,
) -> dict[str, object]:
    limit = _bounded_int(
        args.get("limit"),
        default=config.max_archives_per_run,
        minimum=1,
        maximum=100,
    )
    mode = _optional_str(args.get("mode")) or config.mode
    return run_dream_cycle(
        store,
        config,
        mode=mode,
        stale_after_days=stale_after_days,
        limit=limit,
    )


def handle_prune_stale(
    store: ContinuityStore, args: dict[str, Any], *, stale_after_days: int = 180
) -> dict[str, object]:
    dry_run = _bool(args.get("dry_run"), True)
    mode = str(args.get("mode") or "archive").strip().lower()
    if mode not in {"archive", "delete"}:
        return {"success": False, "error": "mode must be archive or delete"}
    limit = _bounded_int(args.get("limit"), default=20, minimum=1, maximum=100)
    candidates = find_stale_candidates(
        store.list_records(), stale_after_days=stale_after_days, limit=limit
    )
    archived_ids: list[str] = []
    deleted_ids: list[str] = []
    if not dry_run:
        for candidate in candidates:
            if mode == "delete":
                store.delete_record(candidate.record_id)
                deleted_ids.append(candidate.record_id)
            else:
                if store.archive_record(
                    candidate.record_id,
                    reason=candidate.reason,
                    superseded_by=candidate.superseded_by,
                ):
                    archived_ids.append(candidate.record_id)
    return {
        "success": True,
        "dry_run": dry_run,
        "mode": mode,
        "candidates": [candidate.to_dict() for candidate in candidates],
        "archived_ids": archived_ids,
        "deleted_ids": deleted_ids,
    }


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
        "retrieval_role": hit.retrieval_role,
        "activation": hit.activation,
        "activation_trace": list(hit.activation_trace),
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


def _bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


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
