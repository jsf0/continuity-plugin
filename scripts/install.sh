#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/install.sh [--dry-run]

Installs the continuity memory plugin into:
  ${HERMES_HOME:-$HOME/.hermes}/plugins/continuity

Options:
  --dry-run   Print what would be installed without writing files.
  -h, --help  Show this help.
USAGE
}

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
TARGET_DIR="$HERMES_HOME/plugins/continuity"

cat <<MSG
Hermes Continuity Memory install
  source: $SOURCE_DIR/continuity
  target: $TARGET_DIR
MSG

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry run only; no files written."
  exit 0
fi

mkdir -p "$(dirname "$TARGET_DIR")"
rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR"
cp -R "$SOURCE_DIR/continuity/"* "$TARGET_DIR/"

cat <<MSG

Installed Hermes Continuity Memory plugin to:
  $TARGET_DIR

Enable it with Hermes config and plugin flag:

memory:
  provider: continuity

and:

    hermes plugins enable continuity

Both switches are required and independent; without the plugin enable,
Hermes doctor may still report the provider as active while continuity
tools never appear.

Then restart Hermes or start a new session.
MSG
