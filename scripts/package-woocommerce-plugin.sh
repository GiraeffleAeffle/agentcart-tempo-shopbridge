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
(
  cd "$ROOT_DIR/woocommerce-shopbridge"
  zip -qr "$ZIP_PATH" "$PLUGIN_SLUG" -x "*/.DS_Store" "*/__MACOSX/*"
)

echo "Created $ZIP_PATH"
