#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_DIR="$ROOT_DIR/demo/woocommerce"
COMPOSE_FILE="$DEMO_DIR/docker-compose.yml"
WOO_ZIP="$DEMO_DIR/woocommerce.latest-stable.zip"

export WOO_HOST_PORT="${WOO_HOST_PORT:-18098}"
export WOO_PUBLIC_URL="${WOO_PUBLIC_URL:-http://127.0.0.1:${WOO_HOST_PORT}}"

compose_cmd=(docker compose --project-directory "$DEMO_DIR" -f "$COMPOSE_FILE")

cleanup() {
  if [ "${AGENTCART_PLUGIN_CHECK_KEEP_STACK:-0}" != "1" ]; then
    "${compose_cmd[@]}" down >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if ! command -v docker >/dev/null 2>&1; then
  printf 'docker is required for WordPress Plugin Check.\n' >&2
  exit 127
fi
if ! docker info >/dev/null 2>&1; then
  printf 'docker daemon is not reachable.\n' >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  printf 'curl is required for WordPress Plugin Check setup.\n' >&2
  exit 127
fi

if [ ! -f "$WOO_ZIP" ]; then
  printf 'Downloading WooCommerce plugin archive...\n'
  curl -fL --retry 5 --retry-delay 2 --connect-timeout 30 \
    -o "$WOO_ZIP" \
    https://downloads.wordpress.org/plugin/woocommerce.latest-stable.zip
fi

printf 'Starting WordPress demo services for Plugin Check on %s...\n' "$WOO_PUBLIC_URL"
"${compose_cmd[@]}" up -d db wordpress

printf 'Preparing WordPress, WooCommerce, and ShopBridge...\n'
"${compose_cmd[@]}" run --rm wpcli

printf 'Installing official Plugin Check plugin...\n'
"${compose_cmd[@]}" run --rm --entrypoint wp wpcli \
  plugin install plugin-check --activate --allow-root

printf 'Running official WordPress Plugin Check...\n'
plugin_check_output="$(mktemp)"
if ! "${compose_cmd[@]}" run --rm --entrypoint wp wpcli \
  plugin check agentcart-shopbridge --allow-root | tee "$plugin_check_output"; then
  rm -f "$plugin_check_output"
  exit 1
fi

if ! grep -q 'No errors found' "$plugin_check_output"; then
  printf 'WordPress Plugin Check did not report a clean result.\n' >&2
  rm -f "$plugin_check_output"
  exit 1
fi
rm -f "$plugin_check_output"
