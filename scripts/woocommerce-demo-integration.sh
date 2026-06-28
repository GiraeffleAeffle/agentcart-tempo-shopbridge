#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_DIR="${AGENTCART_WOO_DEMO_DIR:-$ROOT_DIR/demo/woocommerce}"
COMPOSE_FILE="${AGENTCART_WOO_DEMO_COMPOSE_FILE:-$DEMO_DIR/docker-compose.yml}"
BASE_URL="${AGENTCART_WOO_INTEGRATION_BASE_URL:-${AGENTCART_WOO_SMOKE_BASE_URL:-${WOO_PUBLIC_URL:-http://127.0.0.1:${WOO_HOST_PORT:-8098}}}}"
EXPECT_SHIPPING_CENTS="${AGENTCART_WOO_INTEGRATION_EXPECT_SHIPPING_CENTS:-${AGENTCART_WOO_SMOKE_EXPECT_SHIPPING_CENTS:-490}}"
MERCHANT_TOKEN="${AGENTCART_WOO_INTEGRATION_MERCHANT_TOKEN:-${AGENTCART_WOO_SMOKE_MERCHANT_TOKEN:-${AGENTCART_SHOPBRIDGE_TOKEN:-agentcart-woo-demo-token}}}"
RATE_LIMIT_BUCKETS="${AGENTCART_WOO_INTEGRATION_RATE_LIMIT_BUCKETS:-quote,checkout,order_status,refund,cancellation}"

export WOO_PUBLIC_URL="${WOO_PUBLIC_URL:-$BASE_URL}"
compose_cmd=(docker compose --project-directory "$DEMO_DIR" -f "$COMPOSE_FILE")

usage() {
  cat <<'EOF'
Usage: scripts/woocommerce-demo-integration.sh [--skip-rate-limits] [--down] [--down-volumes] [--hard]

Starts or resets the bundled WooCommerce demo shop, then runs the full
ShopBridge endpoint integration harness through HTTP.

Options:
  --skip-rate-limits  Do not exhaust live rate-limit buckets.
  --down              Stop demo services after the harness.
  --down-volumes      Stop demo services and remove volumes after the harness.
  --hard              Remove demo volumes before reseeding.
  -h, --help          Show this help.

Environment:
  WOO_HOST_PORT                             default: 8098
  WOO_PUBLIC_URL                            default: http://127.0.0.1:${WOO_HOST_PORT}
  AGENTCART_WOO_INTEGRATION_BASE_URL        overrides harness base URL
  AGENTCART_WOO_INTEGRATION_MERCHANT_TOKEN  default: agentcart-woo-demo-token
  AGENTCART_WOO_INTEGRATION_RATE_LIMIT_BUCKETS default: quote,checkout,order_status,refund,cancellation
  AGENTCART_WOO_SMOKE_REQUIRE_REAL_REFUND_VERIFIER_EVIDENCE set to 1 for production verifier runs
EOF
}

cleanup=0
cleanup_volumes=0
hard_reset=0
rate_limits=1

while [ "$#" -gt 0 ]; do
  case "$1" in
    --skip-rate-limits)
      rate_limits=0
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

reset_args=(--no-smoke)
if [ "$hard_reset" -eq 1 ]; then
  reset_args+=(--hard)
fi

"$ROOT_DIR/scripts/woocommerce-demo-reset.sh" "${reset_args[@]}"

smoke_args=(
  --base-url "$BASE_URL"
  --expect-shipping-cents "$EXPECT_SHIPPING_CENTS"
  --require-shipping
  --require-vat-lines
  --endpoint-harness
  --merchant-token "$MERCHANT_TOKEN"
)
if [ "$rate_limits" -eq 1 ]; then
  smoke_args+=(--abuse-rate-limits --rate-limit-buckets "$RATE_LIMIT_BUCKETS")
fi

python3 "$ROOT_DIR/scripts/woocommerce-shopbridge-smoke.py" "${smoke_args[@]}"

printf 'WooCommerce ShopBridge endpoint integration harness passed: %s\n' "$BASE_URL"

if [ "$cleanup" -eq 1 ]; then
  printf 'Stopping WooCommerce demo services...\n'
  down_args=(down)
  if [ "$cleanup_volumes" -eq 1 ]; then
    down_args+=(-v)
  fi
  "${compose_cmd[@]}" "${down_args[@]}"
fi
