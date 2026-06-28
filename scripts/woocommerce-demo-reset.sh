#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_DIR="${AGENTCART_WOO_DEMO_DIR:-$ROOT_DIR/demo/woocommerce}"
COMPOSE_FILE="${AGENTCART_WOO_DEMO_COMPOSE_FILE:-$DEMO_DIR/docker-compose.yml}"
WOO_ZIP="$DEMO_DIR/woocommerce.latest-stable.zip"
BASE_URL="${AGENTCART_WOO_SMOKE_BASE_URL:-${WOO_PUBLIC_URL:-http://127.0.0.1:${WOO_HOST_PORT:-8098}}}"
EXPECT_SHIPPING_CENTS="${AGENTCART_WOO_SMOKE_EXPECT_SHIPPING_CENTS:-490}"

export WOO_PUBLIC_URL="${WOO_PUBLIC_URL:-$BASE_URL}"
compose_cmd=(docker compose --project-directory "$DEMO_DIR" -f "$COMPOSE_FILE")

usage() {
  cat <<'EOF'
Usage: scripts/woocommerce-demo-reset.sh [--no-smoke] [--down] [--down-volumes] [--hard]

Resets the bundled WooCommerce demo to a known AgentCart state, reseeds
products, tax, shipping, terms, registry metadata, and ShopBridge settings, then
runs the live ShopBridge smoke test unless --no-smoke is supplied.

Options:
  --no-smoke      Reset and reseed without running the live quote smoke.
  --down          Stop demo services after reset/smoke.
  --down-volumes  Stop demo services and remove volumes after reset/smoke.
  --hard          Remove demo volumes before reset, then rebuild/reseed.
  -h, --help      Show this help.

Environment:
  WOO_HOST_PORT                         default: 8098
  WOO_PUBLIC_URL                        default: http://127.0.0.1:${WOO_HOST_PORT}
  WORDPRESS_IMAGE                       default: wordpress:php8.2-apache
  WORDPRESS_CLI_IMAGE                   default: wordpress:cli-php8.2
  AGENTCART_WOO_SMOKE_BASE_URL          overrides smoke base URL
  AGENTCART_WOO_SMOKE_EXPECT_SHIPPING_CENTS default: 490
EOF
}

run_smoke=1
cleanup=0
cleanup_volumes=0
hard_reset=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --no-smoke)
      run_smoke=0
      shift
      ;;
    --down)
      cleanup=1
      shift
      ;;
    --down-volumes)
      cleanup=1
      cleanup_volumes=1
      shift
      ;;
    --hard)
      hard_reset=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  printf 'docker is required for the WooCommerce demo reset.\n' >&2
  exit 127
fi
if ! docker info >/dev/null 2>&1; then
  printf 'docker daemon is not reachable.\n' >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  printf 'curl is required for the WooCommerce demo reset.\n' >&2
  exit 127
fi

if [ ! -f "$WOO_ZIP" ]; then
  printf 'Downloading WooCommerce plugin archive...\n'
  curl -fL --retry 5 --retry-delay 2 --connect-timeout 30 \
    -o "$WOO_ZIP" \
    https://downloads.wordpress.org/plugin/woocommerce.latest-stable.zip
fi

if [ "$hard_reset" -eq 1 ]; then
  printf 'Removing existing WooCommerce demo containers and volumes...\n'
  "${compose_cmd[@]}" down -v
fi

printf 'Starting WooCommerce demo services...\n'
"${compose_cmd[@]}" up -d db wordpress

printf 'Resetting and reseeding WooCommerce demo state...\n'
"${compose_cmd[@]}" run --rm -e AGENTCART_DEMO_RESET=1 wpcli

printf 'Waiting for ShopBridge capability endpoint at %s...\n' "$BASE_URL"
for _ in $(seq 1 60); do
  if curl -fsS "$BASE_URL/wp-json/agentcart/v1/capability" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -fsS "$BASE_URL/wp-json/agentcart/v1/capability" >/dev/null

if [ "$run_smoke" -eq 1 ]; then
  printf 'Running live ShopBridge quote smoke...\n'
  python3 "$ROOT_DIR/scripts/woocommerce-shopbridge-smoke.py" \
    --base-url "$BASE_URL" \
    --expect-shipping-cents "$EXPECT_SHIPPING_CENTS" \
    --require-shipping \
    --require-vat-lines
fi

printf 'WooCommerce demo reset complete: %s\n' "$BASE_URL"

if [ "$cleanup" -eq 1 ]; then
  printf 'Stopping WooCommerce demo services...\n'
  down_args=(down)
  if [ "$cleanup_volumes" -eq 1 ]; then
    down_args+=(-v)
  fi
  "${compose_cmd[@]}" "${down_args[@]}"
fi
