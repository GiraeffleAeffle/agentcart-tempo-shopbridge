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
(
  cd "$ROOT_DIR/gateway"
  zip -qr "$ZIP_PATH" "$SKILL_SLUG" \
    -x "*/.DS_Store" "*/__MACOSX/*" "*/__pycache__/*" "*.pyc"
)

echo "Created $ZIP_PATH"
