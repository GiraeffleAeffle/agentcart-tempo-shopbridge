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
webhook_pid=""
cleanup() {
  if [ -n "$pid" ]; then
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" >/dev/null 2>&1 || true
  fi
  if [ -n "$webhook_pid" ]; then
    kill "$webhook_pid" >/dev/null 2>&1 || true
    wait "$webhook_pid" >/dev/null 2>&1 || true
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

alert_port="$(
  python3 - <<'PY'
import socket

sock = socket.socket()
sock.bind(("127.0.0.1", 0))
print(sock.getsockname()[1])
sock.close()
PY
)"

python3 - "$tmpdir/alerts.jsonl" "$alert_port" >"$tmpdir/webhook.log" 2>&1 <<'PY' &
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

path = sys.argv[1]
port = int(sys.argv[2])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return

    def do_POST(self):
        length = int(self.headers.get("content-length") or "0")
        body = self.rfile.read(length)
        event = {
            "path": self.path,
            "authorization": self.headers.get("authorization"),
            "event": self.headers.get("x-agentcart-event"),
            "event_id": self.headers.get("x-agentcart-event-id"),
            "body": json.loads(body.decode("utf-8")),
        }
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        self.send_response(204)
        self.end_headers()


HTTPServer(("127.0.0.1", port), Handler).serve_forever()
PY
webhook_pid=$!

AGENTCART_VERIFIER_REPLAY_STORE_PATH="$tmpdir/replay/store.json" \
AGENTCART_VERIFIER_REPLAY_JOURNAL_PATH="$tmpdir/replay/journal.jsonl" \
STRIPE_SANDBOX_SECRET_KEY=sk_test_dummy \
STRIPE_PROFILE_ID=profile_test_dummy \
MPP_SECRET_KEY=mpp_dummy_secret \
AGENTCART_PAYMENT_VERIFIER_TOKEN=verifier_dummy \
AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY=true \
AGENTCART_VERIFIER_REQUIRE_REPLAY_JOURNAL=true \
AGENTCART_VERIFIER_ALERT_WEBHOOK_URL="http://127.0.0.1:$alert_port/agentcart-verifier-alerts" \
AGENTCART_VERIFIER_ALERT_WEBHOOK_TOKEN=alert_dummy \
AGENTCART_VERIFIER_ALERT_THROTTLE_SECONDS=0 \
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

unauthorized_metrics = subprocess.run(
    ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", f"http://127.0.0.1:{port}/metrics"],
    check=True,
    text=True,
    stdout=subprocess.PIPE,
)
assert unauthorized_metrics.stdout == "401", unauthorized_metrics.stdout

metrics_result = subprocess.run(
    ["curl", "-fsS", "-H", "authorization: Bearer verifier_dummy", f"http://127.0.0.1:{port}/metrics"],
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
assert metrics["replay_journal"]["configured"] is True, metrics["replay_journal"]
assert metrics["replay_journal"]["required"] is True, metrics["replay_journal"]
assert metrics["replay_journal"]["appended"] == 3, metrics["replay_journal"]
assert metrics["replay_journal"]["failed"] == 0, metrics["replay_journal"]
assert metrics["replay_journal"]["entry_count"] == 3, metrics["replay_journal"]
assert metrics["alerts"]["sent"] == 1, metrics["alerts"]
assert metrics["alerts"]["last_delivery"]["state"] == "sent", metrics["alerts"]

journal_path = work / "replay" / "journal.jsonl"
journal_raw = journal_path.read_text(encoding="utf-8")
assert "tempo_tx_replay_001" not in journal_raw, journal_raw
journal = [json.loads(line) for line in journal_raw.splitlines() if line.strip()]
assert [entry["event"] for entry in journal] == ["claim_accepted", "idempotent_replay", "replay_conflict"], journal
assert {entry["bucket"] for entry in journal} == {"payments"}, journal
assert all(len(entry["reference_hash"]) == 64 for entry in journal), journal
assert all(entry["metadata"]["quote_hash"] == quote_hash for entry in journal), journal

alerts_path = work / "alerts.jsonl"
alerts = [json.loads(line) for line in alerts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
assert len(alerts) == 1, alerts
assert alerts[0]["authorization"] == "Bearer alert_dummy", alerts
assert alerts[0]["event"] == "verifier.alert", alerts
alert = alerts[0]["body"]
assert alert["schema"] == "agentcart.verifier_alert_notification.v1", alert
assert alert["severity"] == "warning", alert
assert alert["code"] == "replay_conflict", alert
assert alert["alert"]["operation"] == "payment", alert
assert alert["alert"]["rail"] == "tempo-mpp", alert

print("verifier replay smoke ok")
PY
