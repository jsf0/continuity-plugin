"""Configuration for the continuity memory provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

VALID_SESSION_STRATEGIES = frozenset({"per-repo", "per-directory", "global", "per-session"})


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
    vector_enabled: bool = False
    vector_backend: str = "none"
    embedding_model: str | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> ContinuityConfig:
        data = value or {}
        vector = data.get("vector") if isinstance(data.get("vector"), dict) else {}
        strategy = str(data.get("session_strategy") or "per-repo")
        if strategy not in VALID_SESSION_STRATEGIES:
            strategy = "per-repo"
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
            vector_enabled=_bool(vector.get("enabled"), False),
            vector_backend=str(vector.get("backend") or "none"),
            embedding_model=_optional_str(vector.get("embedding_model")),
        )


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
