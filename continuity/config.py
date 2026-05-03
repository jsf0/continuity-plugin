"""Configuration for the continuity memory provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALID_SESSION_STRATEGIES = frozenset({"per-repo", "per-directory", "global", "per-session"})
VALID_VECTOR_BACKENDS = frozenset({"none", "sqlite-hash", "hash", "sqlite-json"})


@dataclass(frozen=True)
class PinnedSystemPromptConfig:
    """Configuration for continuity records pinned into the system prompt."""

    enabled: bool = False
    max_chars: int = 1200
    max_records: int = 5
    kinds: tuple[str, ...] = ("user_preference", "project_convention")
    min_importance: float = 0.75


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
    pinned_system_prompt: PinnedSystemPromptConfig = field(default_factory=PinnedSystemPromptConfig)

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> ContinuityConfig:
        data = value or {}
        vector = data.get("vector") if isinstance(data.get("vector"), dict) else {}
        pinned = (
            data.get("pinned_system_prompt")
            if isinstance(data.get("pinned_system_prompt"), dict)
            else {}
        )
        strategy = str(data.get("session_strategy") or "per-repo")
        if strategy not in VALID_SESSION_STRATEGIES:
            strategy = "per-repo"
        vector_backend = str(vector.get("backend") or "none")
        if vector_backend not in VALID_VECTOR_BACKENDS:
            vector_backend = "none"
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
            pinned_system_prompt=PinnedSystemPromptConfig(
                enabled=_bool(pinned.get("enabled"), False),
                max_chars=max(200, _int(pinned.get("max_chars"), 1200)),
                max_records=max(1, _int(pinned.get("max_records"), 5)),
                kinds=tuple(_string_list(pinned.get("kinds")))
                or ("user_preference", "project_convention"),
                min_importance=min(1.0, max(0.0, _float(pinned.get("min_importance"), 0.75))),
            ),
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


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
