#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"

if ! (
  cd "$ROOT_DIR/gateway"
  node -e "await import('stripe'); await import('mppx');" >/dev/null 2>&1
); then
  printf 'stripe/mppx Node dependencies unavailable; skipping verifier replay smoke\n'
  exit 0
fi

tmpdir="$(mktemp -d)"
pid=""
cleanup() {
  if [ -n "$pid" ]; then
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" >/dev/null 2>&1 || true
  fi
  rm -rf "$tmpdir"
}
trap cleanup EXIT

port="$(
  python3 - <<'PY'
import socket

sock = socket.socket()
sock.bind(("127.0.0.1", 0))
print(sock.getsockname()[1])
sock.close()
PY
)"

AGENTCART_VERIFIER_REPLAY_STORE_PATH="$tmpdir/replay/store.json" \
STRIPE_SANDBOX_SECRET_KEY=sk_test_dummy \
STRIPE_PROFILE_ID=profile_test_dummy \
MPP_SECRET_KEY=mpp_dummy_secret \
AGENTCART_PAYMENT_VERIFIER_TOKEN=verifier_dummy \
AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY=true \
STRIPE_MPP_VERIFIER_PORT="$port" \
  node "$ROOT_DIR/gateway/scripts/stripe-mpp-verifier.mjs" >"$tmpdir/verifier.log" 2>&1 &
pid=$!

for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

python3 - <<'PY' "$tmpdir" "$port"
import json
import pathlib
import subprocess
import sys

work = pathlib.Path(sys.argv[1])
port = sys.argv[2]
quote_hash = "0" * 64
contract_a = "a" * 64
contract_b = "b" * 64


def payload(contract: str) -> dict:
    return {
        "operation": "payment",
        "quote_hash": quote_hash,
        "payment_contract_hash": contract,
        "expected": {
            "amount_cents": 1840,
            "currency": "EUR",
            "rail": "tempo-mpp",
            "payment_contract_hash": contract,
            "tempo_network": "testnet",
            "tempo_recipient": "0xabc",
        },
        "payment_receipt": {
            "method": "tempo-mpp",
            "amount_cents": 1840,
            "currency": "EUR",
            "quote_hash": quote_hash,
            "payment_contract_hash": contract,
            "external_value_proof": {
                "provider": "tempo_mpp",
                "state": "succeeded",
                "network": "testnet",
                "body": {
                    "amount": "18.40",
                    "recipient": "0xabc",
                    "transaction_reference": "tempo_tx_replay_001",
                },
            },
        },
    }


def post(name: str, body: dict) -> tuple[int, dict]:
    path = work / f"{name}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(
        [
            "curl",
            "-sS",
            "-w",
            "\n%{http_code}",
            "-H",
            "authorization: Bearer verifier_dummy",
            "-H",
            "content-type: application/json",
            "--data-binary",
            f"@{path}",
            f"http://127.0.0.1:{port}/agentcart/verify",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    data, status = result.stdout.rsplit("\n", 1)
    return int(status), json.loads(data)


status1, body1 = post("first", payload(contract_a))
assert status1 == 200 and body1["ok"] is True and not body1.get("idempotent_replay"), (status1, body1)

status2, body2 = post("same", payload(contract_a))
assert status2 == 200 and body2["ok"] is True and body2.get("idempotent_replay") is True, (status2, body2)

status3, body3 = post("conflict", payload(contract_b))
assert status3 == 409 and body3.get("replay_conflict") is True, (status3, body3)

metrics_result = subprocess.run(
    ["curl", "-fsS", f"http://127.0.0.1:{port}/metrics"],
    check=True,
    text=True,
    stdout=subprocess.PIPE,
)
metrics = json.loads(metrics_result.stdout)
assert metrics["schema"] == "agentcart.verifierMetrics.v1", metrics
assert metrics["by_operation"]["payment"]["total"] == 3, metrics["by_operation"]
assert metrics["by_operation"]["payment"]["ok"] == 2, metrics["by_operation"]
assert metrics["by_operation"]["payment"]["rejected"] == 1, metrics["by_operation"]
assert metrics["by_rail"]["tempo-mpp"]["total"] == 3, metrics["by_rail"]
assert metrics["rejections"]["replay_conflict"] == 1, metrics["rejections"]
assert metrics["settlement"]["demo_settlement_verified"] == 2, metrics["settlement"]
assert metrics["settlement"]["idempotent_replay"] == 1, metrics["settlement"]
assert metrics["latency_ms"]["count"] >= 4, metrics["latency_ms"]

print("verifier replay smoke ok")
PY
