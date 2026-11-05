"""Configuration for the continuity memory provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALID_SESSION_STRATEGIES = frozenset({"per-repo", "per-directory", "global", "per-session"})
VALID_VECTOR_BACKENDS = frozenset(
    {"none", "sqlite-hash", "hash", "sqlite-json", "sentence-transformers"}
)
VALID_RERANKER_BACKENDS = frozenset({"none", "sentence-transformers", "cross-encoder"})


@dataclass(frozen=True)
class PinnedSystemPromptConfig:
    """Configuration for continuity records pinned into the system prompt."""

    enabled: bool = True
    include_records: bool = True
    max_chars: int = 1200
    max_records: int = 5
    kinds: tuple[str, ...] = ("user_preference", "project_convention")
    min_importance: float = 0.75


@dataclass(frozen=True)
class AssociationGraphConfig:
    """Configuration for associative graph retrieval."""

    enabled: bool = True
    edge_creation_threshold: float = 0.25
    out_degree_cap: int = 20
    candidate_limit: int = 250
    hop_decay: float = 0.6
    activation_threshold: float = 0.3
    max_hops: int = 2


@dataclass(frozen=True)
class RetrievalGateConfig:
    """Configuration for conservative retrieval gates and thresholds."""

    min_base_relevance: float = 0.35
    min_vector_relevance: float = 0.05
    min_vector_only_relevance: float = 2.75
    weak_vector_only: bool = True
    facet_compatibility: bool = True
    memory_meta: bool = True
    low_information: bool = True
    project_status_anchor: bool = True
    personal_project: bool = True
    activation_anchor: bool = True
    strong_personal_anchor_reranker_bypass: bool = True
    strong_fts_anchor_reranker_bypass: bool = True
    graph_inclusion_respects_reranker: bool = True
    graph_reranker_respect_floor: float = 0.005
    self_referential_echo_penalty: bool = True
    self_referential_echo_weight: float = 1.0


@dataclass(frozen=True)
class DreamConfig:
    """Configuration for scheduled offline continuity maintenance."""

    enabled: bool = False
    schedule: str = "03:30"
    timezone: str = "UTC"
    mode: str = "report"
    max_archives_per_run: int = 20
    run_on_initialize: bool = True
    run_on_turn: bool = True


@dataclass(frozen=True)
class ContinuityConfig:
    """Runtime configuration for continuity memory."""

    max_records: int = 5
    max_chars: int = 1800
    min_score: float = 0.1
    include_sources: bool = True
    include_scores: bool = False
    save_turn_observations: bool = True
    consolidate_on_session_end: bool = True
    consolidate_min_turns: int = 3
    session_strategy: str = "per-repo"
    project_scope_boost: float = 1.0
    stale_after_days: int = 180
    observation_max_chars: int = 4000
    vector_enabled: bool = False
    vector_backend: str = "none"
    embedding_model: str | None = None
    embedding_batch_size: int = 32
    embedding_normalize: bool = True
    reranker_enabled: bool = False
    reranker_backend: str = "none"
    reranker_model: str | None = None
    reranker_min_score: float = 0.15
    reranker_weight: float = 2.0
    reranker_top_k: int = 20
    retrieval_gates: RetrievalGateConfig = field(default_factory=RetrievalGateConfig)
    pinned_system_prompt: PinnedSystemPromptConfig = field(default_factory=PinnedSystemPromptConfig)
    association_graph: AssociationGraphConfig = field(default_factory=AssociationGraphConfig)
    dream: DreamConfig = field(default_factory=DreamConfig)

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> ContinuityConfig:
        data = value or {}
        vector = data.get("vector") if isinstance(data.get("vector"), dict) else {}
        reranker = data.get("reranker") if isinstance(data.get("reranker"), dict) else {}
        pinned = (
            data.get("pinned_system_prompt")
            if isinstance(data.get("pinned_system_prompt"), dict)
            else {}
        )
        association = (
            data.get("association_graph") if isinstance(data.get("association_graph"), dict) else {}
        )
        gates = data.get("retrieval_gates") if isinstance(data.get("retrieval_gates"), dict) else {}
        dream = data.get("dream") if isinstance(data.get("dream"), dict) else {}
        strategy = str(data.get("session_strategy") or "per-repo")
        if strategy not in VALID_SESSION_STRATEGIES:
            strategy = "per-repo"
        vector_backend = str(vector.get("backend") or "none")
        if vector_backend not in VALID_VECTOR_BACKENDS:
            vector_backend = "none"
        reranker_backend = str(reranker.get("backend") or "none")
        if reranker_backend not in VALID_RERANKER_BACKENDS:
            reranker_backend = "none"
        dream_mode = str(dream.get("mode") or "report").strip().lower()
        if dream_mode not in {"report", "archive-safe", "archive-all-candidates"}:
            dream_mode = "report"
        dream_schedule = _schedule_str(dream.get("schedule"), "03:30")
        return cls(
            max_records=max(1, _int(data.get("max_records"), 5)),
            max_chars=max(200, _int(data.get("max_chars"), 1800)),
            min_score=min(1.0, max(0.0, _float(data.get("min_score"), 0.1))),
            include_sources=_bool(data.get("include_sources"), True),
            include_scores=_bool(data.get("include_scores"), False),
            save_turn_observations=_bool(data.get("save_turn_observations"), True),
            consolidate_on_session_end=_bool(data.get("consolidate_on_session_end"), True),
            consolidate_min_turns=max(1, _int(data.get("consolidate_min_turns"), 3)),
            session_strategy=strategy,
            project_scope_boost=max(0.0, _float(data.get("project_scope_boost"), 1.0)),
            stale_after_days=max(1, _int(data.get("stale_after_days"), 180)),
            observation_max_chars=max(200, _int(data.get("observation_max_chars"), 4000)),
            vector_enabled=_bool(vector.get("enabled"), False),
            vector_backend=vector_backend,
            embedding_model=_optional_str(vector.get("embedding_model")),
            embedding_batch_size=max(1, _int(vector.get("batch_size"), 32)),
            embedding_normalize=_bool(vector.get("normalize"), True),
            reranker_enabled=_bool(reranker.get("enabled"), False),
            reranker_backend=reranker_backend,
            reranker_model=_optional_str(reranker.get("model")),
            reranker_min_score=min(1.0, max(0.0, _float(reranker.get("min_score"), 0.15))),
            reranker_weight=max(0.0, _float(reranker.get("weight"), 2.0)),
            reranker_top_k=max(1, _int(reranker.get("top_k"), 20)),
            retrieval_gates=RetrievalGateConfig(
                min_base_relevance=min(
                    10.0, max(0.0, _float(gates.get("min_base_relevance"), 0.35))
                ),
                min_vector_relevance=min(
                    1.0, max(0.0, _float(gates.get("min_vector_relevance"), 0.05))
                ),
                min_vector_only_relevance=min(
                    10.0, max(0.0, _float(gates.get("min_vector_only_relevance"), 2.75))
                ),
                weak_vector_only=_bool(gates.get("weak_vector_only"), True),
                facet_compatibility=_bool(gates.get("facet_compatibility"), True),
                memory_meta=_bool(gates.get("memory_meta"), True),
                low_information=_bool(gates.get("low_information"), True),
                project_status_anchor=_bool(gates.get("project_status_anchor"), True),
                personal_project=_bool(gates.get("personal_project"), True),
                activation_anchor=_bool(gates.get("activation_anchor"), True),
                strong_personal_anchor_reranker_bypass=_bool(
                    gates.get("strong_personal_anchor_reranker_bypass"), True
                ),
                strong_fts_anchor_reranker_bypass=_bool(
                    gates.get("strong_fts_anchor_reranker_bypass"), True
                ),
                graph_inclusion_respects_reranker=_bool(
                    gates.get("graph_inclusion_respects_reranker"), True
                ),
                graph_reranker_respect_floor=min(
                    1.0, max(0.0, _float(gates.get("graph_reranker_respect_floor"), 0.005))
                ),
                self_referential_echo_penalty=_bool(
                    gates.get("self_referential_echo_penalty"), True
                ),
                self_referential_echo_weight=min(
                    5.0,
                    max(0.0, _float(gates.get("self_referential_echo_weight"), 1.0)),
                ),
            ),
            pinned_system_prompt=PinnedSystemPromptConfig(
                enabled=_bool(pinned.get("enabled"), True),
                include_records=_bool(pinned.get("include_records"), True),
                max_chars=max(200, _int(pinned.get("max_chars"), 1200)),
                max_records=max(0, _int(pinned.get("max_records"), 5)),
                kinds=tuple(_string_list(pinned.get("kinds")))
                or ("user_preference", "project_convention"),
                min_importance=min(1.0, max(0.0, _float(pinned.get("min_importance"), 0.75))),
            ),
            association_graph=AssociationGraphConfig(
                enabled=_bool(association.get("enabled"), True),
                edge_creation_threshold=min(
                    1.0,
                    max(0.0, _float(association.get("edge_creation_threshold"), 0.25)),
                ),
                out_degree_cap=max(1, _int(association.get("out_degree_cap"), 20)),
                candidate_limit=max(1, _int(association.get("candidate_limit"), 250)),
                hop_decay=min(1.0, max(0.0, _float(association.get("hop_decay"), 0.6))),
                activation_threshold=min(
                    1.0,
                    max(0.0, _float(association.get("activation_threshold"), 0.3)),
                ),
                max_hops=max(1, _int(association.get("max_hops"), 2)),
            ),
            dream=DreamConfig(
                enabled=_bool(dream.get("enabled"), False),
                schedule=dream_schedule,
                timezone=str(dream.get("timezone") or "UTC").strip() or "UTC",
                mode=dream_mode,
                max_archives_per_run=max(1, _int(dream.get("max_archives_per_run"), 20)),
                run_on_initialize=_bool(dream.get("run_on_initialize"), True),
                run_on_turn=_bool(dream.get("run_on_turn"), True),
            ),
        )


def _schedule_str(value: object, default: str) -> str:
    text = str(value or default).strip()
    parts = text.split(":")
    if len(parts) != 2:
        return default
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return default
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return default
    return f"{hour:02d}:{minute:02d}"


def _int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
        return []
    return [str(item).strip() for item in value if str(item).strip()]
