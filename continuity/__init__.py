"""Continuity memory provider for Hermes Agent.

Phase 1 implements only provider discovery, initialization, and the
``continuity_status`` tool. Persistent records and retrieval arrive in later
phases described in ``docs/SPEC.md``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from continuity.config import ContinuityConfig
from continuity.extraction import extract_records_from_messages
from continuity.project import ProjectContext, detect_project
from continuity.retrieval import ContinuityRetriever, RetrievalHit
from continuity.store import ContinuityStore
from continuity.tools import (
    ALL_TOOL_SCHEMAS,
    handle_add,
    handle_delete,
    handle_get,
    handle_search,
)
from continuity.tools import (
    CONTINUITY_STATUS_SCHEMA as CONTINUITY_STATUS_SCHEMA,
)

try:  # pragma: no cover - exercised when running inside Hermes Agent.
    from agent.memory_provider import MemoryProvider
except ModuleNotFoundError:  # Standalone test/dev mode without Hermes on sys.path.

    class MemoryProvider:  # type: ignore[no-redef]
        """Minimal compatibility base for standalone tests.

        Hermes itself supplies ``agent.memory_provider.MemoryProvider``. This
        fallback keeps the standalone GitHub plugin testable before installation.
        """



class _RegistrationContext(Protocol):
    def register_memory_provider(self, provider: object) -> None: ...


class ContinuityProvider(MemoryProvider):
    """Local-first structured continuity memory provider.

    Phase 1 intentionally does not retrieve or persist context records yet. It
    only proves Hermes can discover, initialize, and call the provider.
    """

    def __init__(self) -> None:
        self._initialized = False
        self._session_id = ""
        self._hermes_home: Path | None = None
        self._data_dir: Path | None = None
        self._platform = ""
        self._agent_context = ""
        self._store: ContinuityStore | None = None
        self._config = ContinuityConfig()
        self._project: ProjectContext | None = None
        self._turn_index = 0

    @property
    def name(self) -> str:
        return "continuity"

    def is_available(self) -> bool:
        """Return whether the provider can run in this environment."""
        return True

    def initialize(self, session_id: str, **kwargs: object) -> None:
        """Initialize provider-local state for a Hermes session."""
        hermes_home_value = kwargs.get("hermes_home")
        hermes_home = Path(str(hermes_home_value)).expanduser() if hermes_home_value else Path.home() / ".hermes"
        data_dir = hermes_home / "continuity"
        data_dir.mkdir(parents=True, exist_ok=True)

        self._session_id = session_id
        self._hermes_home = hermes_home
        self._data_dir = data_dir
        self._platform = str(kwargs.get("platform") or "")
        self._agent_context = str(kwargs.get("agent_context") or "")
        raw_config = kwargs.get("continuity_config")
        self._config = ContinuityConfig.from_mapping(raw_config if isinstance(raw_config, dict) else {})
        self._project = detect_project()
        self._store = ContinuityStore(data_dir / "continuity.db")
        self._store.migrate()
        self._initialized = True

    def system_prompt_block(self) -> str:
        """Keep Phase 1 prompt impact at zero."""
        return ""

    def prefetch(
        self,
        query: str,
        *,
        session_id: str = "",
        scope_project: str | None = None,
    ) -> str:
        """Retrieve compact relevant continuity context for the current turn."""
        _ = session_id
        if not self._store or not query.strip():
            return ""
        effective_scope = scope_project or self._project_display_name()
        hits = ContinuityRetriever(self._store).search(
            query,
            scope_project=effective_scope,
            limit=self._config.max_records,
        )
        selected = [hit for hit in hits if hit.score >= self._config.min_score]
        output, included = _format_prefetch_context(
            selected,
            max_chars=self._config.max_chars,
            include_sources=self._config.include_sources,
            include_scores=self._config.include_scores,
        )
        self._store.log_retrieval_event(
            query=query,
            selected_ids=[hit.record.id for hit in included],
            skipped_ids=[hit.record.id for hit in selected if hit.record.id not in {i.record.id for i in included}],
            scores={hit.record.id: hit.score for hit in selected},
            max_chars=self._config.max_chars,
        )
        return output

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        """No-op until retrieval/background prefetch exists."""
        _ = (query, session_id)

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        """Persist a lightweight per-turn observation for later consolidation."""
        if not self._store or not self._config.save_turn_observations:
            return
        effective_session_id = session_id or self._session_id
        self._turn_index += 1
        self._store.add_session_observation(
            session_id=effective_session_id,
            turn_index=self._turn_index,
            user_content=user_content,
            assistant_content=assistant_content,
            max_chars=self._config.observation_max_chars,
        )

    def on_session_end(self, messages: list[dict[str, Any]]) -> None:
        """Consolidate clear durable memories at session boundaries."""
        if not self._store or not self._config.consolidate_on_session_end:
            return
        user_turns = sum(1 for message in messages if message.get("role") == "user")
        if user_turns < self._config.consolidate_min_turns:
            return
        records = extract_records_from_messages(
            session_id=self._session_id,
            messages=messages,
            scope_project=self._project_display_name(),
        )
        for record in records:
            self._store.upsert_record(record)
        self._store.mark_session_observations_consolidated(self._session_id)

    def on_pre_compress(self, messages: list[dict[str, Any]]) -> str:
        """No-op until pre-compression extraction exists."""
        _ = messages
        return ""

    def on_memory_write(self, action: str, target: str, content: str) -> None:
        """No-op until built-in memory mirroring exists."""
        _ = (action, target, content)

    def on_delegation(
        self,
        task: str,
        result: str,
        *,
        child_session_id: str = "",
        **kwargs: object,
    ) -> None:
        """No-op until delegation observation storage exists."""
        _ = (task, result, child_session_id, kwargs)

    def get_tool_schemas(self) -> list[dict[str, object]]:
        return ALL_TOOL_SCHEMAS

    def handle_tool_call(self, tool_name: str, args: dict[str, Any], **kwargs: object) -> str:
        _ = kwargs
        if tool_name == "continuity_status":
            return json.dumps(self._status_payload(), ensure_ascii=False)
        if tool_name in {
            "continuity_search",
            "continuity_get",
            "continuity_add",
            "continuity_delete",
        } and self._store is None:
            return json.dumps(
                {"success": False, "error": "continuity provider is not initialized"},
                ensure_ascii=False,
            )
        if tool_name == "continuity_search" and self._store is not None:
            return json.dumps(handle_search(self._store, args), ensure_ascii=False)
        if tool_name == "continuity_get" and self._store is not None:
            return json.dumps(handle_get(self._store, args), ensure_ascii=False)
        if tool_name == "continuity_add" and self._store is not None:
            return json.dumps(handle_add(self._store, args), ensure_ascii=False)
        if tool_name == "continuity_delete" and self._store is not None:
            return json.dumps(handle_delete(self._store, args), ensure_ascii=False)
        return json.dumps(
            {
                "success": False,
                "error": f"Unknown continuity tool: {tool_name}",
            },
            ensure_ascii=False,
        )

    def shutdown(self) -> None:
        """Phase 1 has no resources to release."""

    def _status_payload(self) -> dict[str, object]:
        return {
            "success": True,
            "provider": self.name,
            "initialized": self._initialized,
            "session_id": self._session_id,
            "hermes_home": str(self._hermes_home) if self._hermes_home else None,
            "data_dir": str(self._data_dir) if self._data_dir else None,
            "platform": self._platform,
            "agent_context": self._agent_context,
            "record_count": self._store.count_records() if self._store else 0,
            "db_path": str(self._store.db_path) if self._store else None,
            "current_project": self._project.project_id if self._project else None,
            "current_project_display_name": self._project.display_name if self._project else None,
            "max_records": self._config.max_records,
            "max_chars": self._config.max_chars,
            "vector_enabled": self._config.vector_enabled,
            "phase": "phase-5-session-consolidation",
        }

    def _project_display_name(self) -> str | None:
        return self._project.display_name if self._project else None


def _format_prefetch_context(
    hits: list[RetrievalHit],
    *,
    max_chars: int,
    include_sources: bool,
    include_scores: bool,
) -> tuple[str, list[RetrievalHit]]:
    if not hits:
        return "", []
    lines = ["Relevant continuity memory:"]
    included: list[RetrievalHit] = []
    for hit in hits:
        candidate_lines = _format_hit(len(included) + 1, hit, include_sources, include_scores)
        candidate_output = "\n".join([*lines, *candidate_lines])
        if len(candidate_output) > max_chars:
            continue
        lines.extend(candidate_lines)
        included.append(hit)
    if not included:
        return "", []
    return "\n".join(lines), included


def _format_hit(
    index: int,
    hit: RetrievalHit,
    include_sources: bool,
    include_scores: bool,
) -> list[str]:
    record = hit.record
    meta_parts = [record.kind]
    if record.scope_project:
        meta_parts.append(f"project={record.scope_project}")
    meta_parts.append(f"confidence={record.confidence:.2f}")
    if include_scores:
        meta_parts.append(f"score={hit.score:.2f}")
    lines = [f"{index}. [{' | '.join(meta_parts)}]", f"   {record.summary}"]
    if include_sources and record.sources:
        source_text = "; ".join(_format_source(source) for source in record.sources)
        if source_text:
            lines.append(f"   Sources: {source_text}")
    return lines


def _format_source(source: object) -> str:
    source_type = getattr(source, "type", "source")
    source_id = getattr(source, "id", None)
    source_range = getattr(source, "range", None)
    source_uri = getattr(source, "uri", None)
    label = f"{source_type}:{source_id or source_uri or 'unknown'}"
    if source_range:
        label += f" {source_range}"
    return label


def register(ctx: _RegistrationContext) -> None:
    """Register this memory provider with Hermes' plugin loader."""
    ctx.register_memory_provider(ContinuityProvider())
