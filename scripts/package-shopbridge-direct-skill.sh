#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_SLUG="shopbridge-direct-skill"
SKILL_DIR="$ROOT_DIR/gateway/$SKILL_SLUG"
DIST_DIR="$ROOT_DIR/dist"
ZIP_PATH="$DIST_DIR/$SKILL_SLUG.zip"

if [ ! -f "$SKILL_DIR/SKILL.md" ]; then
  echo "Skill file not found: $SKILL_DIR/SKILL.md" >&2
  exit 1
fi

if [ ! -f "$SKILL_DIR/scripts/shopbridge-command.py" ]; then
  echo "Skill command helper not found: $SKILL_DIR/scripts/shopbridge-command.py" >&2
  exit 1
fi

mkdir -p "$DIST_DIR"
rm -f "$ZIP_PATH"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
STAGING_DIR="$TMP_DIR/$SKILL_SLUG"
mkdir -p "$STAGING_DIR"

(
  cd "$SKILL_DIR"
  find . -type f | LC_ALL=C sort | while IFS= read -r path; do
    rel="${path#./}"
    case "$rel" in
      .DS_Store|__MACOSX/*|*/.DS_Store|*/__MACOSX/*|__pycache__/*|*/__pycache__/*|*.pyc) continue ;;
    esac
    mkdir -p "$STAGING_DIR/$(dirname "$rel")"
    cp -p "$path" "$STAGING_DIR/$rel"
  done
)
find "$STAGING_DIR" -exec touch -t 202001010000 {} +
(
  cd "$TMP_DIR"
  find "$SKILL_SLUG" -type f | LC_ALL=C sort | zip -X -q "$ZIP_PATH" -@
)

echo "Created $ZIP_PATH"
