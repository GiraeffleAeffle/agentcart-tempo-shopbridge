#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_SLUG="agentcart-shopbridge"
PLUGIN_DIR="$ROOT_DIR/woocommerce-shopbridge/$PLUGIN_SLUG"
DIST_DIR="$ROOT_DIR/dist"
ZIP_PATH="$DIST_DIR/$PLUGIN_SLUG.zip"

if [ ! -f "$PLUGIN_DIR/$PLUGIN_SLUG.php" ]; then
  echo "Plugin entry file not found: $PLUGIN_DIR/$PLUGIN_SLUG.php" >&2
  exit 1
fi

mkdir -p "$DIST_DIR"
rm -f "$ZIP_PATH"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
STAGING_DIR="$TMP_DIR/$PLUGIN_SLUG"
mkdir -p "$STAGING_DIR"

(
  cd "$PLUGIN_DIR"
  find . -type f | LC_ALL=C sort | while IFS= read -r path; do
    rel="${path#./}"
    case "$rel" in
      .DS_Store|__MACOSX/*|*/.DS_Store|*/__MACOSX/*) continue ;;
    esac
    mkdir -p "$STAGING_DIR/$(dirname "$rel")"
    cp -p "$path" "$STAGING_DIR/$rel"
  done
)
find "$STAGING_DIR" -exec touch -t 202001010000 {} +
(
  cd "$TMP_DIR"
  find "$PLUGIN_SLUG" -type f | LC_ALL=C sort | zip -X -q "$ZIP_PATH" -@
)

echo "Created $ZIP_PATH"
