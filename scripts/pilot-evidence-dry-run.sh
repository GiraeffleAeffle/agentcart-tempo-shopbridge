#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
report_out="${1:-}"
tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/agentcart-pilot-evidence.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT

sample_root="$tmpdir/pilot-evidence/example-shop"
payment_env="$tmpdir/payment.env"
report_path="${report_out:-$tmpdir/pilot-evidence-report.json}"

mkdir -p "$(dirname "$report_path")"

cat >"$payment_env" <<'ENV'
WOOCOMMERCE_MODE=plugin
AGENTCART_CHECKOUT_MODE=external_verifier_only
AGENTCART_PAYMENT_VERIFIER_URL=https://verifier.agentcart.test/stripe-mpp/verify
AGENTCART_PAYMENT_VERIFIER_TOKEN=verifier-token
AGENTCART_VERIFIER_REPLAY_STORE_DRIVER=sqlite
AGENTCART_VERIFIER_REPLAY_STORE_PATH=/data/verifier/replay-store.sqlite
AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY=true
AGENTCART_SIGNED_REQUEST_MODE=require_mutations
AGENTCART_SIGNED_REQUEST_SECRET=shared-signing-secret
WOOCOMMERCE_SIGNED_REQUEST_SECRET=shared-signing-secret
ENV

python3 "$ROOT_DIR/scripts/collect-pilot-evidence.py" \
  --write-sample "$sample_root" >/dev/null

python3 "$ROOT_DIR/scripts/collect-pilot-evidence.py" \
  --pilot-evidence-dir "$sample_root/pilot" \
  --buyer-agent-evidence-dir "$sample_root/buyer-agents" \
  --payment-env-file "$payment_env" \
  --report-out "$report_path" >/dev/null

python3 - "$report_path" <<'PY'
import json
import pathlib
import sys

report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
if report.get("schema") != "agentcart.pilot_evidence_runner.v1":
    raise SystemExit("unexpected pilot evidence report schema")
if report.get("status") != "passed":
    raise SystemExit("pilot evidence dry run did not pass")
if report.get("release_decision", {}).get("attach_this_report") is not True:
    raise SystemExit("pilot evidence report is not marked attachable")
PY

printf 'pilot evidence dry run ok: %s\n' "$report_path"
