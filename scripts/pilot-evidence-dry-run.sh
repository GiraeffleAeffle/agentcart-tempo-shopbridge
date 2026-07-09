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
AGENTCART_PAYMENT_VERIFIER_TOKEN=vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
AGENTCART_VERIFIER_REPLAY_STORE_DRIVER=sqlite
AGENTCART_VERIFIER_REPLAY_STORE_PATH=/data/verifier/replay-store.sqlite
AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY=true
AGENTCART_SIGNED_REQUEST_MODE=require_mutations
AGENTCART_SIGNED_REQUEST_SECRET=ssssssssssssssssssssssssssssssssssssssss
WOOCOMMERCE_SIGNED_REQUEST_SECRET=ssssssssssssssssssssssssssssssssssssssss
ENV

python3 "$ROOT_DIR/scripts/collect-pilot-evidence.py" \
  --write-sample "$sample_root" >/dev/null

python3 - "$sample_root" <<'PY'
import pathlib
import sys

sample_root = pathlib.Path(sys.argv[1])
for path in sample_root.rglob("*.md"):
    if path.name == "README.md":
        continue
    scope = "buyer_agent_runtime" if "buyer-agents" in path.parts else "pilot_gate"
    owner_id = path.parent.name
    evidence_id = path.stem
    path.write_text(
        f"# {evidence_id}\n\n"
        f"- Scope: `{scope}`\n"
        f"- Owner id: `{owner_id}`\n"
        "- Recorded at: 2026-07-09T18:00:00Z\n"
        "- Operator: Pilot evidence dry-run operator\n"
        "- Command or source: `scripts/pilot-evidence-dry-run.sh`\n\n"
        "## Evidence\n\n"
        "This temporary fixture records a completed command, observed result, acceptance "
        "criteria, and retained artifact reference so the successful release-gate path is exercised.\n",
        encoding="utf-8",
    )
PY

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
if report.get("release_decision", {}).get("invalid_evidence_count") != 0:
    raise SystemExit("pilot evidence dry run reported invalid evidence")
PY

printf 'pilot evidence dry run ok: %s\n' "$report_path"
