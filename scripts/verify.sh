#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

section() {
  printf '\n== %s ==\n' "$1"
}

section "Python tests: gateway"
(
  cd "$ROOT_DIR/gateway"
  python3 -m unittest discover -s tests
)

section "Python tests: household-os"
(
  cd "$ROOT_DIR/household-os"
  python3 -m unittest discover -s tests
)

section "Python 3.11 compatibility"
py311_files=(
  gateway/agentcart.py
  gateway/scripts/household-agent-demo.py
  gateway/scripts/registry_record.py
  gateway/openclaw-skill/scripts/agentcart-command.py
  gateway/shopbridge-direct-skill/scripts/shopbridge-command.py
  household-os/household_os.py
  scripts/build-release-manifest.py
  scripts/check-buyer-agent-adapter-examples.py
  scripts/check-shopbridge-endpoint-contract.py
  scripts/check-wordpress-plugin-package.py
  scripts/check-wordpress-plugin-review.py
  scripts/check-wordpress-official-gates.py
  scripts/check-woocommerce-compatibility-matrix.py
  scripts/check-buyer-agent-matrix.py
  scripts/check-ap2-mandate-mapping.py
  scripts/check-beta-release-readiness.py
  scripts/collect-pilot-evidence.py
  scripts/check-ucp-a2a-profiles.py
  scripts/check-pilot-readiness.py
  scripts/check-production-payment-profile.py
  scripts/check-prompt-injection-corpus.py
  scripts/check-quote-reliability-matrix.py
  scripts/check-repo-positioning.py
  scripts/stamp-release-version.py
  scripts/verify-release.py
  scripts/verify-verifier-fixtures.py
  scripts/woocommerce-shopbridge-smoke.py
)
if command -v python3.11 >/dev/null 2>&1; then
  (
    cd "$ROOT_DIR"
    python3.11 - "${py311_files[@]}" <<'PY'
import pathlib
import py_compile
import sys
import tempfile

with tempfile.TemporaryDirectory() as tmp:
    for file_name in sys.argv[1:]:
        cfile = pathlib.Path(tmp) / (file_name.replace("/", "__") + ".pyc")
        py_compile.compile(file_name, cfile=str(cfile), doraise=True)
PY
  )
elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker run --rm \
    -v "$ROOT_DIR:/repo:ro" \
    -w /repo \
    python:3.11-slim \
    python - "${py311_files[@]}" <<'PY'
import pathlib
import py_compile
import sys
import tempfile

with tempfile.TemporaryDirectory() as tmp:
    for file_name in sys.argv[1:]:
        cfile = pathlib.Path(tmp) / (file_name.replace("/", "__") + ".pyc")
        py_compile.compile(file_name, cfile=str(cfile), doraise=True)
PY
else
  printf 'python3.11 and docker daemon unavailable; skipping Python 3.11 compatibility compile\n'
fi

section "WooCommerce plugin syntax"
if command -v php >/dev/null 2>&1; then
  php -l "$ROOT_DIR/woocommerce-shopbridge/agentcart-shopbridge/agentcart-shopbridge.php"
  php -l "$ROOT_DIR/woocommerce-shopbridge/agentcart-shopbridge/uninstall.php"
else
  printf 'php not installed; skipping php -l\n'
fi
bash -n "$ROOT_DIR/scripts/woocommerce-demo-smoke.sh"
bash -n "$ROOT_DIR/scripts/woocommerce-demo-reset.sh"
bash -n "$ROOT_DIR/scripts/woocommerce-demo-integration.sh"
bash -n "$ROOT_DIR/demo/woocommerce/seed-products.sh"
python3 -m py_compile "$ROOT_DIR/scripts/woocommerce-shopbridge-smoke.py"
python3 -m py_compile "$ROOT_DIR/scripts/check-wordpress-plugin-review.py"
python3 -m py_compile "$ROOT_DIR/scripts/check-wordpress-official-gates.py"
python3 "$ROOT_DIR/scripts/check-wordpress-plugin-review.py"
AGENTCART_WORDPRESS_PLUGIN_CHECK_COMMAND="${AGENTCART_WORDPRESS_PLUGIN_CHECK_COMMAND:-$ROOT_DIR/scripts/run-wordpress-plugin-check.sh}" \
  python3 "$ROOT_DIR/scripts/check-wordpress-official-gates.py"
python3 "$ROOT_DIR/scripts/check-shopbridge-endpoint-contract.py" \
  --contract "$ROOT_DIR/gateway/config/shopbridge_endpoint_contract.json" >/dev/null
python3 "$ROOT_DIR/scripts/check-woocommerce-compatibility-matrix.py" \
  --matrix "$ROOT_DIR/gateway/config/woocommerce_compatibility_matrix.json" >/dev/null
python3 -m unittest discover -s "$ROOT_DIR/woocommerce-shopbridge/tests"

section "WooCommerce ShopBridge live smoke"
if [ -n "${AGENTCART_WOO_SMOKE_BASE_URL:-}" ]; then
  smoke_args=(--base-url "$AGENTCART_WOO_SMOKE_BASE_URL")
  if [ -n "${AGENTCART_WOO_SMOKE_EXPECT_SHIPPING_CENTS:-}" ]; then
    smoke_args+=(--expect-shipping-cents "$AGENTCART_WOO_SMOKE_EXPECT_SHIPPING_CENTS")
  fi
  if [ "${AGENTCART_WOO_SMOKE_REQUIRE_SHIPPING:-}" = "1" ]; then
    smoke_args+=(--require-shipping)
  fi
  if [ "${AGENTCART_WOO_SMOKE_REQUIRE_VAT_LINES:-}" = "1" ]; then
    smoke_args+=(--require-vat-lines)
  fi
  if [ "${AGENTCART_WOO_SMOKE_REQUIRE_PRODUCTION_READY:-}" = "1" ]; then
    smoke_args+=(--require-production-ready)
  fi
  python3 "$ROOT_DIR/scripts/woocommerce-shopbridge-smoke.py" "${smoke_args[@]}" >/dev/null
else
  printf 'AGENTCART_WOO_SMOKE_BASE_URL not set; skipping live WooCommerce smoke\n'
fi

section "Stripe MPP verifier syntax"
(
  cd "$ROOT_DIR/gateway"
  npm run stripe:mpp:check
  node --check scripts/verifier-sqlite-replay-store.mjs
  bash -n scripts/stripe-link-mpp-smoke.sh
  bash -n scripts/verifier-replay-smoke.sh
  bash -n scripts/verifier-sqlite-replay-smoke.sh
)

section "Verifier contract fixtures"
python3 "$ROOT_DIR/scripts/verify-verifier-fixtures.py" >/dev/null
bash "$ROOT_DIR/gateway/scripts/verifier-replay-smoke.sh"
bash "$ROOT_DIR/gateway/scripts/verifier-sqlite-replay-smoke.sh"

section "Pilot readiness checklist"
python3 "$ROOT_DIR/scripts/check-pilot-readiness.py" \
  --checklist "$ROOT_DIR/gateway/config/pilot_beta_checklist.json" >/dev/null

section "Production payment profile shape"
python3 "$ROOT_DIR/scripts/check-production-payment-profile.py" \
  --env-file "$ROOT_DIR/deploy/home-server/.env.example" \
  --env-file "$ROOT_DIR/deploy/home-server/.env.production-payment.example" \
  --allow-placeholders >/dev/null

section "External beta release evidence gate"
if [ "${AGENTCART_BETA_RELEASE_GATE:-0}" = "1" ]; then
  : "${AGENTCART_PILOT_EVIDENCE_DIR:?set AGENTCART_PILOT_EVIDENCE_DIR for external beta release checks}"
  : "${AGENTCART_BUYER_AGENT_EVIDENCE_DIR:?set AGENTCART_BUYER_AGENT_EVIDENCE_DIR for external beta release checks}"
  : "${AGENTCART_PAYMENT_ENV_FILE:?set AGENTCART_PAYMENT_ENV_FILE for external beta release checks}"
  evidence_args=()
  if [ -n "${AGENTCART_PILOT_EVIDENCE_REPORT_OUT:-}" ]; then
    evidence_args+=(--report-out "$AGENTCART_PILOT_EVIDENCE_REPORT_OUT")
  fi
  if [ "${AGENTCART_WOO_COMPATIBILITY_SMOKE:-0}" = "1" ]; then
    evidence_args+=(--run-woocommerce-smoke)
  fi
  if [ "${AGENTCART_WOO_COMPATIBILITY_INCLUDE_OPTIONAL:-0}" = "1" ]; then
    evidence_args+=(--include-optional-woocommerce)
  fi
  if [ -n "${AGENTCART_WOO_COMPATIBILITY_ENTRY:-}" ]; then
    evidence_args+=(--woocommerce-entry "$AGENTCART_WOO_COMPATIBILITY_ENTRY")
  fi
  python3 "$ROOT_DIR/scripts/collect-pilot-evidence.py" \
    --pilot-evidence-dir "$AGENTCART_PILOT_EVIDENCE_DIR" \
    --buyer-agent-evidence-dir "$AGENTCART_BUYER_AGENT_EVIDENCE_DIR" \
    --payment-env-file "$AGENTCART_PAYMENT_ENV_FILE" \
    "${evidence_args[@]}" >/dev/null
else
  printf 'AGENTCART_BETA_RELEASE_GATE=1 not set; skipping evidence-required external beta gate\n'
fi

section "Buyer-agent test matrix"
python3 "$ROOT_DIR/scripts/check-buyer-agent-matrix.py" \
  --matrix "$ROOT_DIR/gateway/config/buyer_agent_test_matrix.json" >/dev/null

section "Buyer-agent adapter examples"
python3 "$ROOT_DIR/scripts/check-buyer-agent-adapter-examples.py" \
  --config "$ROOT_DIR/gateway/config/buyer_agent_adapter_examples.json" \
  --matrix "$ROOT_DIR/gateway/config/buyer_agent_test_matrix.json" >/dev/null

section "AP2-style mandate mapping"
python3 "$ROOT_DIR/scripts/check-ap2-mandate-mapping.py" \
  --mapping "$ROOT_DIR/gateway/config/ap2_mandate_mapping.json" \
  --verify-test-refs >/dev/null

section "UCP/A2A profile mappings"
python3 "$ROOT_DIR/scripts/check-ucp-a2a-profiles.py" \
  --profiles "$ROOT_DIR/gateway/config/ucp_a2a_profiles.json" \
  --verify-test-refs >/dev/null

section "Prompt-injection corpus"
python3 "$ROOT_DIR/scripts/check-prompt-injection-corpus.py" \
  --corpus "$ROOT_DIR/gateway/config/prompt_injection_corpus.json" \
  --verify-test-refs >/dev/null

section "Quote reliability matrix"
python3 "$ROOT_DIR/scripts/check-quote-reliability-matrix.py" \
  --matrix "$ROOT_DIR/gateway/config/quote_reliability_matrix.json" \
  --verify-test-refs >/dev/null

section "Repo production positioning"
python3 "$ROOT_DIR/scripts/check-repo-positioning.py" >/dev/null
python3 "$ROOT_DIR/scripts/stamp-release-version.py" 1.2.3-beta.4 --check >/dev/null
bash -n "$ROOT_DIR/scripts/prepare-semantic-release.sh"
node -e "const c=require(process.argv[1]); if (!Array.isArray(c.plugins) || !c.plugins.length) process.exit(1)" "$ROOT_DIR/release.config.cjs"

section "Compose config"
AGENTCART_PUBLIC_URL=http://localhost:8099 AGENTCART_TOKEN=verify-token AGENTCART_REGISTRY_SUBMIT_TOKEN=verify-registry-token \
  docker compose -f "$ROOT_DIR/gateway/docker-compose.yml" config >/dev/null
docker compose -f "$ROOT_DIR/demo/woocommerce/docker-compose.yml" config >/dev/null
docker compose \
  --env-file "$ROOT_DIR/deploy/home-server/.env.example" \
  -f "$ROOT_DIR/deploy/home-server/docker-compose.yml" \
  --profile homeassistant \
  --profile woocommerce-demo \
  config >/dev/null
docker compose \
  --env-file "$ROOT_DIR/deploy/home-server/.env.example" \
  --env-file "$ROOT_DIR/deploy/home-server/.env.production-payment.example" \
  -f "$ROOT_DIR/deploy/home-server/docker-compose.yml" \
  --profile woocommerce-demo \
  config >/dev/null

section "Package WooCommerce plugin"
"$ROOT_DIR/scripts/package-woocommerce-plugin.sh"
zip_listing="$(unzip -l "$ROOT_DIR/dist/agentcart-shopbridge.zip")"
grep -q "agentcart-shopbridge/agentcart-shopbridge.php" <<<"$zip_listing"
grep -q "agentcart-shopbridge/readme.txt" <<<"$zip_listing"
grep -q "agentcart-shopbridge/uninstall.php" <<<"$zip_listing"
python3 "$ROOT_DIR/scripts/check-wordpress-plugin-package.py" --zip "$ROOT_DIR/dist/agentcart-shopbridge.zip"

section "Package ShopBridge direct skill"
bash -n "$ROOT_DIR/scripts/package-shopbridge-direct-skill.sh"
"$ROOT_DIR/scripts/package-shopbridge-direct-skill.sh"
skill_zip_listing="$(unzip -l "$ROOT_DIR/dist/shopbridge-direct-skill.zip")"
grep -q "shopbridge-direct-skill/SKILL.md" <<<"$skill_zip_listing"
grep -q "shopbridge-direct-skill/scripts/shopbridge-command.py" <<<"$skill_zip_listing"

section "Build release manifest"
python3 "$ROOT_DIR/scripts/build-release-manifest.py"
grep -q '"schema": "agentcart.release.v1"' "$ROOT_DIR/dist/agentcart-release.json"
grep -q '"sha256":' "$ROOT_DIR/dist/agentcart-release.json"
python3 "$ROOT_DIR/scripts/verify-release.py" --manifest "$ROOT_DIR/dist/agentcart-release.json" --root "$ROOT_DIR" >/dev/null
release_sig="$(mktemp "${TMPDIR:-/tmp}/agentcart-release.XXXXXX")"
AGENTCART_RELEASE_SIGNING_KEY="verify-local-release-signing-key" \
  python3 "$ROOT_DIR/scripts/build-release-manifest.py" \
    --signature-out "$release_sig" \
    --signature-key-id verify-local >/dev/null
AGENTCART_RELEASE_SIGNING_KEY="verify-local-release-signing-key" \
  python3 "$ROOT_DIR/scripts/verify-release.py" \
    --manifest "$ROOT_DIR/dist/agentcart-release.json" \
    --root "$ROOT_DIR" \
    --signature "$release_sig" \
    --trusted-signature-key-id verify-local \
    --require-signature >/dev/null
rm -f "$release_sig"

section "Gateway Docker image"
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  image="agentcart-gateway-verify:latest"
  container="agentcart-gateway-verify"
  docker build -q -t "$image" "$ROOT_DIR/gateway" >/dev/null
  docker rm -f "$container" >/dev/null 2>&1 || true
  docker run -d --rm --name "$container" \
    -e AGENTCART_BIND=0.0.0.0 \
    -e AGENTCART_TOKEN=verify-token \
    -e AGENTCART_REGISTRY_SUBMIT_TOKEN=verify-registry-token \
    -p 127.0.0.1:18099:8099 "$image" >/dev/null
  cleanup() {
    docker rm -f "$container" >/dev/null 2>&1 || true
  }
  trap cleanup EXIT
  for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:18099/health" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  for path in /health /presentation.html /demo /onboarding.html /protocol-fields.html /payment-options.html /shopbridge-stack.html /intent-auction-overview.html /architecture.html /roadmap.html /registry; do
    curl -fsS "http://127.0.0.1:18099$path" >/dev/null
  done
  cleanup
  trap - EXIT
else
  printf 'docker daemon unavailable; skipping gateway image smoke\n'
fi

section "Verification complete"
