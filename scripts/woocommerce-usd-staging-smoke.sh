#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${AGENTCART_WOO_USD_SMOKE_BASE_URL:-https://woo-usd.agentcart.eu}"
SECRETS_ENV_FILE="${AGENTCART_WOO_USD_SECRETS_ENV_FILE:-$ROOT_DIR/.secrets/agentcart-staging-usd.env}"
with_endpoint_harness=0

load_env_file() {
  local line key value
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ""|\#*)
        continue
        ;;
    esac

    key="${line%%=*}"
    value="${line#*=}"
    if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || [ "$key" = "$line" ]; then
      continue
    fi

    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    export "$key=$value"
  done < "$1"
}

usage() {
  cat <<'EOF'
Usage: scripts/woocommerce-usd-staging-smoke.sh [--endpoint-harness]

Smoke tests the USD Tempo WooCommerce staging shop. The default quote check uses
US shipping and USD currency and does not require VAT lines.

Options:
  --endpoint-harness  Also run mutable checkout/cancellation/refund endpoint probes.
                      Uses a synthetic proof unless AGENTCART_WOO_SMOKE_TEMPO_MPP_PROOF_URL is set.
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
    load_env_file "$SECRETS_ENV_FILE"
  fi
  if [ -z "${STAGING_SHOPBRIDGE_TOKEN:-}" ]; then
    printf 'STAGING_SHOPBRIDGE_TOKEN is required for --endpoint-harness. Source %s or set it manually.\n' "$SECRETS_ENV_FILE" >&2
    exit 2
  fi
  case "${STAGING_TEMPO_SETTLEMENT_MODE:-disabled}" in
    verify|VERIFY|Verify)
      if [ -z "${AGENTCART_WOO_SMOKE_TEMPO_MPP_PROOF_URL:-}" ]; then
        printf 'STAGING_TEMPO_SETTLEMENT_MODE=verify requires a real Tempo proof. Run scripts/woocommerce-usd-mppx-settlement-smoke.sh for the live settlement/refund harness, or set AGENTCART_WOO_SMOKE_TEMPO_MPP_PROOF_URL for a prepared paid resource.\n' >&2
        exit 2
      fi
      ;;
  esac
  args+=(--endpoint-harness --merchant-token "$STAGING_SHOPBRIDGE_TOKEN")
  if [ -n "${STAGING_SIGNED_REQUEST_SECRET:-}" ]; then
    args+=(--signed-request-secret "$STAGING_SIGNED_REQUEST_SECRET")
  fi
fi

python3 "$ROOT_DIR/scripts/woocommerce-shopbridge-smoke.py" "${args[@]}"
