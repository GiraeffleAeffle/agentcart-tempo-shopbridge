#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${STRIPE_MPP_ENV_FILE:-$ROOT_DIR/.env.stripe-mpp.local}"
VERIFIER_BASE_URL="${STRIPE_MPP_VERIFIER_BASE_URL:-http://127.0.0.1:4260}"
PAID_URL="${STRIPE_MPP_PAID_URL:-$VERIFIER_BASE_URL/stripe-mpp/paid}"
AMOUNT_CENTS="${STRIPE_MPP_TEST_AMOUNT_CENTS:-100}"
CURRENCY="${STRIPE_MPP_TEST_CURRENCY:-eur}"
QUOTE_HASH="${STRIPE_MPP_TEST_QUOTE_HASH:-stripe_link_cli_smoke_quote}"
MERCHANT_ID="${STRIPE_MPP_TEST_MERCHANT_ID:-woocommerce-demo-shop}"
LINK_PAYMENT_METHOD_ID="${LINK_PAYMENT_METHOD_ID:-}"
LINK_SPEND_REQUEST_ID="${LINK_SPEND_REQUEST_ID:-}"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

if [ -z "${STRIPE_PROFILE_ID:-}" ]; then
  printf 'STRIPE_PROFILE_ID is required. Put it in %s or export it.\n' "$ENV_FILE" >&2
  exit 2
fi

if ! command -v node >/dev/null 2>&1; then
  printf 'node is required for link-cli.\n' >&2
  exit 2
fi

LINK_CLI=(npx --yes @stripe/link-cli)

printf 'Checking Stripe MPP verifier at %s\n' "$VERIFIER_BASE_URL"
curl -fsS "$VERIFIER_BASE_URL/health" >/tmp/agentcart-stripe-mpp-health.json
python3 - <<'PY'
import json
body = json.load(open('/tmp/agentcart-stripe-mpp-health.json'))
if not body.get('ok'):
    raise SystemExit(f"verifier not ready: {body}")
print("verifier", body.get("service"), "ready")
print("profile_present", bool(body.get("stripe_profile_id")))
PY

printf 'Checking Link CLI auth status\n'
"${LINK_CLI[@]}" auth status --format json >/tmp/agentcart-link-auth.json
if ! python3 - <<'PY'
import json, sys
body = json.load(open('/tmp/agentcart-link-auth.json'))
item = body[0] if isinstance(body, list) and body else body
sys.exit(0 if item.get('authenticated') else 1)
PY
then
  cat >&2 <<'EOF'
Link CLI is not authenticated yet.

Run:
  npx --yes @stripe/link-cli auth login
  npx --yes @stripe/link-cli payment-methods list

Then rerun this script with:
  LINK_PAYMENT_METHOD_ID=csmrpd_... gateway/scripts/stripe-link-mpp-smoke.sh
EOF
  exit 2
fi

if [ -z "$LINK_PAYMENT_METHOD_ID" ] && [ -z "$LINK_SPEND_REQUEST_ID" ]; then
  printf 'LINK_PAYMENT_METHOD_ID was not set. Available Link payment methods:\n' >&2
  "${LINK_CLI[@]}" payment-methods list
  cat >&2 <<'EOF'

Rerun with:
  LINK_PAYMENT_METHOD_ID=csmrpd_... gateway/scripts/stripe-link-mpp-smoke.sh

Or use an existing approved spend request:
  LINK_SPEND_REQUEST_ID=lsrq_... gateway/scripts/stripe-link-mpp-smoke.sh
EOF
  exit 2
fi

if [ -z "$LINK_SPEND_REQUEST_ID" ]; then
  CONTEXT="AgentCart Stripe MPP sandbox smoke test for a quote-bound WooCommerce order. This creates a one-time shared payment token for the configured test Stripe profile and pays the local AgentCart verifier endpoint."
  printf 'Creating Link test spend request for %s %s on profile %s\n' "$AMOUNT_CENTS" "$CURRENCY" "$STRIPE_PROFILE_ID"
  "${LINK_CLI[@]}" spend-request create \
    --payment-method-id "$LINK_PAYMENT_METHOD_ID" \
    --credential-type shared_payment_token \
    --network-id "$STRIPE_PROFILE_ID" \
    --amount "$AMOUNT_CENTS" \
    --currency "$CURRENCY" \
    --context "$CONTEXT" \
    --line-item "name:AgentCart Stripe MPP smoke,unit_amount:$AMOUNT_CENTS,quantity:1" \
    --total "type:total,display_text:Total,amount:$AMOUNT_CENTS" \
    --test \
    --approve \
    --format json >/tmp/agentcart-link-spend-request.json
  LINK_SPEND_REQUEST_ID="$(python3 - <<'PY'
import json
body = json.load(open('/tmp/agentcart-link-spend-request.json'))
def walk(value):
    if isinstance(value, dict):
        for key in ("id", "spend_request_id"):
            found = value.get(key)
            if isinstance(found, str) and found.startswith("lsrq_"):
                print(found)
                return True
        return any(walk(v) for v in value.values())
    if isinstance(value, list):
        return any(walk(v) for v in value)
    return False
if not walk(body):
    raise SystemExit("Could not find lsrq_ spend request id in link-cli output")
PY
)"
fi

printf 'Using spend request %s\n' "$LINK_SPEND_REQUEST_ID"
PAYLOAD="$(python3 - <<PY
import json, os
print(json.dumps({
    "operation": "payment",
    "quote_hash": os.environ.get("QUOTE_HASH", "$QUOTE_HASH"),
    "payment_receipt": {
        "id": "receipt_link_cli_smoke",
        "method": "stripe-card-mpp",
        "rail": "stripe-card-mpp",
        "amount_cents": int(os.environ.get("AMOUNT_CENTS", "$AMOUNT_CENTS")),
        "currency": os.environ.get("CURRENCY", "$CURRENCY").upper(),
        "quote_hash": os.environ.get("QUOTE_HASH", "$QUOTE_HASH"),
    },
    "expected": {
        "amount_cents": int(os.environ.get("AMOUNT_CENTS", "$AMOUNT_CENTS")),
        "currency": os.environ.get("CURRENCY", "$CURRENCY").upper(),
        "merchant_id": os.environ.get("MERCHANT_ID", "$MERCHANT_ID"),
        "rail": "stripe-card-mpp",
        "stripe_profile_id": os.environ["STRIPE_PROFILE_ID"],
    },
}, separators=(",", ":")))
PY
)"

printf 'Running Link CLI MPP payment against %s\n' "$PAID_URL"
"${LINK_CLI[@]}" mpp pay "$PAID_URL" \
  --spend-request-id "$LINK_SPEND_REQUEST_ID" \
  --method POST \
  --header "Content-Type: application/json" \
  --data "$PAYLOAD" \
  --format json >/tmp/agentcart-link-mpp-pay.json

python3 - <<'PY'
import json
body = json.load(open('/tmp/agentcart-link-mpp-pay.json'))
text = json.dumps(body)
print("link_mpp_pay_completed", True)
for key in ("PaymentIntent", "payment_intent", "pi_"):
    if key in text:
        print("stripe_payment_reference_present", True)
        break
else:
    print("stripe_payment_reference_present", False)
PY
