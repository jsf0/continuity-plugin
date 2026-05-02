"""Continuity memory provider for Hermes Agent.

Phase 1 implements only provider discovery, initialization, and the
``continuity_status`` tool. Persistent records and retrieval arrive in later
phases described in ``docs/SPEC.md``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from continuity.store import ContinuityStore

try:  # pragma: no cover - exercised when running inside Hermes Agent.
    from agent.memory_provider import MemoryProvider
except ModuleNotFoundError:  # Standalone test/dev mode without Hermes on sys.path.

    class MemoryProvider:  # type: ignore[no-redef]
        """Minimal compatibility base for standalone tests.

        Hermes itself supplies ``agent.memory_provider.MemoryProvider``. This
        fallback keeps the standalone GitHub plugin testable before installation.
        """


CONTINUITY_STATUS_SCHEMA: dict[str, object] = {
    "name": "continuity_status",
    "description": "Show status for the local continuity memory provider.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


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
        self._store = ContinuityStore(data_dir / "continuity.db")
        self._store.migrate()
        self._initialized = True

    def system_prompt_block(self) -> str:
        """Keep Phase 1 prompt impact at zero."""
        return ""

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Return no recalled context until the retrieval phase is implemented."""
        _ = (query, session_id)
        return ""

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        """No-op until retrieval/background prefetch exists."""
        _ = (query, session_id)

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        """No-op until session observation storage exists."""
        _ = (user_content, assistant_content, session_id)

    def on_session_end(self, messages: list[dict[str, Any]]) -> None:
        """No-op until session consolidation exists."""
        _ = messages

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
        return [CONTINUITY_STATUS_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: dict[str, Any], **kwargs: object) -> str:
        _ = (args, kwargs)
        if tool_name == "continuity_status":
            return json.dumps(self._status_payload(), ensure_ascii=False)
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
            "vector_enabled": False,
            "phase": "phase-1-skeleton",
        }


def register(ctx: _RegistrationContext) -> None:
    """Register this memory provider with Hermes' plugin loader."""
    ctx.register_memory_provider(ContinuityProvider())
