#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if command -v uv >/dev/null 2>&1; then
  cd "$ROOT_DIR"
  uv run python scripts/demo-retrieval.py "$@"
else
  python3 "$ROOT_DIR/scripts/demo-retrieval.py" "$@"
fi
