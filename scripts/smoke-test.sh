#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT

export HERMES_HOME="$TMP_HOME"
export TERMINAL_CWD="$ROOT_DIR"

"$ROOT_DIR/scripts/install.sh" >/dev/null

if command -v uv >/dev/null 2>&1; then
  PY=(uv run python)
else
  PY=(python)
fi

"${PY[@]}" - <<'PY'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ["TERMINAL_CWD"])
HERMES_HOME = Path(os.environ["HERMES_HOME"])

hermes_agent = Path.home() / ".hermes" / "hermes-agent"
provider = None
if hermes_agent.exists():
    sys.path.insert(0, str(hermes_agent))
    try:
        from plugins.memory import load_memory_provider

        provider = load_memory_provider("continuity")
    except Exception:
        provider = None

if provider is None:
    sys.path.insert(0, str(ROOT))
    from continuity import ContinuityProvider

    provider = ContinuityProvider()

provider.initialize(
    "phase8-smoke",
    hermes_home=str(HERMES_HOME),
    continuity_config={"vector": {"enabled": True, "backend": "sqlite-hash"}},
)

add = json.loads(
    provider.handle_tool_call(
        "continuity_add",
        {
            "id": "r_phase8_smoke",
            "kind": "lesson_learned",
            "title": "Phase 8 smoke test memory",
            "summary": "patch lint can falsely report Rust 2015 async errors; verify with cargo check.",
            "scope_project": ROOT.name,
            "tags": ["openbsd", "rust", "lint"],
            "skill_links": [
                {
                    "skill_name": "devops/openbsd-rust-dev-loop",
                    "reason": "Relevant for OpenBSD Rust verification.",
                    "confidence": 0.95,
                    "source": "explicit_user",
                }
            ],
        },
    )
)
assert add["success"] is True, add
assert add["skill_links"][0]["skill_name"] == "devops/openbsd-rust-dev-loop", add

search = json.loads(
    provider.handle_tool_call(
        "continuity_search",
        {"query": "patch lint rust cargo check", "scope_project": ROOT.name, "limit": 3},
    )
)
assert search["success"] is True, search
assert search["results"][0]["id"] == "r_phase8_smoke", search
assert search["results"][0]["skill_links"][0]["skill_name"] == "devops/openbsd-rust-dev-loop", search

prefetch = provider.prefetch("patch lint rust cargo check", scope_project=ROOT.name)
assert "Related skills: devops/openbsd-rust-dev-loop" in prefetch, prefetch

provider.on_memory_write("add", "memory", f"{ROOT.name} gotcha: delegate_task subagent can hang.")
mirrored = json.loads(
    provider.handle_tool_call(
        "continuity_search",
        {"query": "worker stuck", "scope_project": ROOT.name, "limit": 3},
    )
)
assert mirrored["success"] is True, mirrored
assert any(result["id"].startswith("mirror_memory_") for result in mirrored["results"]), mirrored

status = json.loads(provider.handle_tool_call("continuity_status", {}))
assert status["phase"] == "phase-7.6-skill-links", status
assert status["record_count"] >= 2, status
assert status["vector_available"] is True, status

print("smoke test ok")
PY
