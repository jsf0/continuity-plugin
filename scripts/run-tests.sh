#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if command -v uv >/dev/null 2>&1; then
  uv run ruff format --check .
  uv run ruff check .
  uv run pytest tests/ -q
else
  python -m ruff format --check .
  python -m ruff check .
  python -m pytest tests/ -q
fi
