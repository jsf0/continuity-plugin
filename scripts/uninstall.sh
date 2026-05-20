#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/uninstall.sh [--dry-run] [--remove-data]

Removes the installed continuity plugin code from:
  ${HERMES_HOME:-$HOME/.hermes}/plugins/continuity

By default this preserves runtime memory data under:
  ${HERMES_HOME:-$HOME/.hermes}/continuity

Options:
  --dry-run      Print what would be removed without deleting anything.
  --remove-data  Also delete runtime continuity memory data. This is destructive.
  -h, --help     Show this help.
USAGE
}

DRY_RUN=0
REMOVE_DATA=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN=1
      ;;
    --remove-data)
      REMOVE_DATA=1
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

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_DIR="$HERMES_HOME/plugins/continuity"
DATA_DIR="$HERMES_HOME/continuity"

cat <<MSG
Hermes Continuity Memory uninstall
  plugin code: $PLUGIN_DIR
  data dir:    $DATA_DIR
  remove data: $REMOVE_DATA
MSG

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry run only; no files removed."
  exit 0
fi

rm -rf "$PLUGIN_DIR"
echo "Removed plugin code: $PLUGIN_DIR"

if [[ "$REMOVE_DATA" -eq 1 ]]; then
  rm -rf "$DATA_DIR"
  echo "Removed continuity data: $DATA_DIR"
else
  cat <<MSG
Preserved continuity data: $DATA_DIR

To remove stored memory data too, rerun with:
  scripts/uninstall.sh --remove-data
MSG
fi

cat <<'MSG'

If your Hermes config still contains:

memory:
  provider: continuity

remove or change that block, then restart Hermes or start a new session.
MSG
