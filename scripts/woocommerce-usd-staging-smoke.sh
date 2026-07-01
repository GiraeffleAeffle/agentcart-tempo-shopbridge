#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${AGENTCART_WOO_USD_SMOKE_BASE_URL:-https://woo-usd.agentcart.eu}"
SECRETS_ENV_FILE="${AGENTCART_WOO_USD_SECRETS_ENV_FILE:-$ROOT_DIR/.secrets/agentcart-staging-usd.env}"
with_endpoint_harness=0

usage() {
  cat <<'EOF'
Usage: scripts/woocommerce-usd-staging-smoke.sh [--endpoint-harness]

Smoke tests the USD Tempo WooCommerce staging shop. The default quote check uses
US shipping and USD currency and does not require VAT lines.

Options:
  --endpoint-harness  Also run mutable checkout/cancellation/refund endpoint probes.
  -h, --help          Show this help.

Environment:
  AGENTCART_WOO_USD_SMOKE_BASE_URL       default: https://woo-usd.agentcart.eu
  AGENTCART_WOO_USD_SECRETS_ENV_FILE     default: .secrets/agentcart-staging-usd.env
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --endpoint-harness)
      with_endpoint_harness=1
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

args=(
  --base-url "$BASE_URL"
  --search tea
  --country US
  --postcode 10001
  --city "New York"
  --address "Demo Street 1"
  --currency USD
  --require-shipping
)

if [ "$with_endpoint_harness" -eq 1 ]; then
  if [ -f "$SECRETS_ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$SECRETS_ENV_FILE"
    set +a
  fi
  if [ -z "${STAGING_SHOPBRIDGE_TOKEN:-}" ]; then
    printf 'STAGING_SHOPBRIDGE_TOKEN is required for --endpoint-harness. Source %s or set it manually.\n' "$SECRETS_ENV_FILE" >&2
    exit 2
  fi
  args+=(--endpoint-harness --merchant-token "$STAGING_SHOPBRIDGE_TOKEN")
fi

python3 "$ROOT_DIR/scripts/woocommerce-shopbridge-smoke.py" "${args[@]}"
