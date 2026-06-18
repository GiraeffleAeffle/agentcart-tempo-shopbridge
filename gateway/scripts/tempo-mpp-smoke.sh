#!/usr/bin/env bash
set -euo pipefail

ACCOUNT="${MPPX_ACCOUNT:-agentcart-test}"
NETWORK="${MPP_SMOKE_NETWORK:-testnet}"
BASE_URL="${MPP_SMOKE_URL:-http://127.0.0.1:4250}"

echo "== mppx account =="
npx mppx account view --network "$NETWORK" --account "$ACCOUNT"

echo
echo "== smoke server readiness =="
curl -fsS "$BASE_URL/health"

echo
echo "== paid request =="
npx mppx "$BASE_URL/paid" --network "$NETWORK" --account "$ACCOUNT" --include

