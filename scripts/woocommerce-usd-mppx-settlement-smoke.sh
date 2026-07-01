#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${AGENTCART_WOO_USD_SMOKE_BASE_URL:-https://woo-usd.agentcart.eu}"
SECRETS_ENV_FILE="${AGENTCART_WOO_USD_SECRETS_ENV_FILE:-$ROOT_DIR/.secrets/agentcart-staging-usd.env}"
GATEWAY_DIR="${AGENTCART_GATEWAY_DIR:-$ROOT_DIR/gateway}"
MPP_BIND="${AGENTCART_WOO_MPP_SMOKE_BIND:-127.0.0.1}"
MPP_PORT="${AGENTCART_WOO_MPP_SMOKE_PORT:-4250}"
MPP_NETWORK="${AGENTCART_WOO_MPP_SMOKE_NETWORK:-testnet}"
MPP_ACCOUNT="${AGENTCART_WOO_MPP_SMOKE_ACCOUNT:-agentcart-test}"
MPP_PROOF_URL="${AGENTCART_WOO_MPP_SMOKE_PROOF_URL:-http://$MPP_BIND:$MPP_PORT/paid}"
MPP_COMMAND="${AGENTCART_WOO_MPP_SMOKE_COMMAND:-npm --prefix $GATEWAY_DIR exec -- mppx}"
server_pid=""

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
    if [ -n "${!key:-}" ]; then
      continue
    fi
    export "$key=$value"
  done < "$1"
}

cleanup() {
  if [ -n "$server_pid" ] && kill -0 "$server_pid" >/dev/null 2>&1; then
    kill "$server_pid" >/dev/null 2>&1 || true
    wait "$server_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

usage() {
  cat <<'EOF'
Usage: scripts/woocommerce-usd-mppx-settlement-smoke.sh

Starts the local AgentCart MPP paid resource, pays it with mppx testnet, and
submits the resulting Tempo proof to the USD WooCommerce staging checkout.

Required:
  .secrets/agentcart-staging-usd.env with STAGING_SHOPBRIDGE_TOKEN and
  STAGING_TEMPO_RECIPIENT_ADDRESS.

Environment:
  AGENTCART_WOO_MPP_SMOKE_ACCOUNT       default: agentcart-test
  AGENTCART_WOO_MPP_SMOKE_NETWORK       default: testnet
  AGENTCART_WOO_MPP_SMOKE_PORT          default: 4250
  AGENTCART_WOO_MPP_SMOKE_COMMAND       default: npm --prefix gateway exec -- mppx
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

if [ -f "$SECRETS_ENV_FILE" ]; then
  load_env_file "$SECRETS_ENV_FILE"
fi

if [ -z "${STAGING_SHOPBRIDGE_TOKEN:-}" ]; then
  printf 'STAGING_SHOPBRIDGE_TOKEN is required. Source %s or set it manually.\n' "$SECRETS_ENV_FILE" >&2
  exit 2
fi
if [ -z "${STAGING_TEMPO_RECIPIENT_ADDRESS:-}" ]; then
  printf 'STAGING_TEMPO_RECIPIENT_ADDRESS is required. Source %s or set it manually.\n' "$SECRETS_ENV_FILE" >&2
  exit 2
fi
if [ ! -d "$GATEWAY_DIR/node_modules/mppx" ]; then
  printf 'mppx dependency is missing. Run `npm ci` in %s first.\n' "$GATEWAY_DIR" >&2
  exit 2
fi

printf 'Checking mppx account %s on %s...\n' "$MPP_ACCOUNT" "$MPP_NETWORK" >&2
npm --prefix "$GATEWAY_DIR" exec -- mppx account view --network "$MPP_NETWORK" --account "$MPP_ACCOUNT" >/dev/null

log_file="$(mktemp "${TMPDIR:-/tmp}/agentcart-mpp-smoke.XXXXXX")"
printf 'Starting MPP paid resource at %s...\n' "$MPP_PROOF_URL" >&2
MPP_SMOKE_BIND="$MPP_BIND" \
MPP_SMOKE_PORT="$MPP_PORT" \
MPP_SMOKE_NETWORK="$MPP_NETWORK" \
MPP_SMOKE_RECIPIENT="$STAGING_TEMPO_RECIPIENT_ADDRESS" \
  node "$GATEWAY_DIR/scripts/mpp-smoke-server.mjs" >"$log_file" 2>&1 &
server_pid="$!"

for _ in $(seq 1 30); do
  if curl -fsS "http://$MPP_BIND:$MPP_PORT/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS "http://$MPP_BIND:$MPP_PORT/health" >/dev/null

STAGING_SHOPBRIDGE_TOKEN="$STAGING_SHOPBRIDGE_TOKEN" \
  python3 "$ROOT_DIR/scripts/woocommerce-shopbridge-smoke.py" \
    --base-url "$BASE_URL" \
    --search tea \
    --country US \
    --postcode 10001 \
    --city "New York" \
    --address "Demo Street 1" \
    --currency USD \
    --require-shipping \
    --endpoint-harness \
    --merchant-token "$STAGING_SHOPBRIDGE_TOKEN" \
    --signed-request-secret "${STAGING_SIGNED_REQUEST_SECRET:-}" \
    --tempo-mpp-proof-url "$MPP_PROOF_URL" \
    --tempo-mpp-command "$MPP_COMMAND" \
    --tempo-mpp-network "$MPP_NETWORK" \
    --tempo-mpp-account "$MPP_ACCOUNT"
