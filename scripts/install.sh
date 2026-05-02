#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
TARGET_DIR="$HERMES_HOME/plugins/continuity"

mkdir -p "$TARGET_DIR"
cp -R "$SOURCE_DIR/continuity/"* "$TARGET_DIR/"

cat <<MSG
Installed Hermes Continuity Memory plugin to:
  $TARGET_DIR

Enable it with:
  hermes config set memory.provider continuity

Then restart Hermes or start a new session.
MSG
