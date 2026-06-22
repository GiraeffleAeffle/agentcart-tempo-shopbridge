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

section "WooCommerce plugin syntax"
if command -v php >/dev/null 2>&1; then
  php -l "$ROOT_DIR/woocommerce-shopbridge/agentcart-shopbridge/agentcart-shopbridge.php"
else
  printf 'php not installed; skipping php -l\n'
fi
python3 -m unittest discover -s "$ROOT_DIR/woocommerce-shopbridge/tests"

section "Stripe MPP verifier syntax"
(
  cd "$ROOT_DIR/gateway"
  npm run stripe:mpp:check
  bash -n scripts/stripe-link-mpp-smoke.sh
)

section "Compose config"
AGENTCART_PUBLIC_URL=http://localhost:8099 AGENTCART_TOKEN=verify-token \
  docker compose -f "$ROOT_DIR/gateway/docker-compose.yml" config >/dev/null
docker compose -f "$ROOT_DIR/demo/woocommerce/docker-compose.yml" config >/dev/null
docker compose \
  --env-file "$ROOT_DIR/deploy/home-server/.env.example" \
  -f "$ROOT_DIR/deploy/home-server/docker-compose.yml" \
  --profile homeassistant \
  --profile woocommerce-demo \
  config >/dev/null

section "Package WooCommerce plugin"
"$ROOT_DIR/scripts/package-woocommerce-plugin.sh"
zip_listing="$(unzip -l "$ROOT_DIR/dist/agentcart-shopbridge.zip")"
grep -q "agentcart-shopbridge/agentcart-shopbridge.php" <<<"$zip_listing"

section "Package ShopBridge direct skill"
bash -n "$ROOT_DIR/scripts/package-shopbridge-direct-skill.sh"
"$ROOT_DIR/scripts/package-shopbridge-direct-skill.sh"
skill_zip_listing="$(unzip -l "$ROOT_DIR/dist/shopbridge-direct-skill.zip")"
grep -q "shopbridge-direct-skill/SKILL.md" <<<"$skill_zip_listing"
grep -q "shopbridge-direct-skill/scripts/shopbridge-command.py" <<<"$skill_zip_listing"

section "Gateway Docker image"
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  image="agentcart-gateway-verify:latest"
  container="agentcart-gateway-verify"
  docker build -q -t "$image" "$ROOT_DIR/gateway" >/dev/null
  docker rm -f "$container" >/dev/null 2>&1 || true
  docker run -d --rm --name "$container" -e AGENTCART_BIND=0.0.0.0 -p 127.0.0.1:18099:8099 "$image" >/dev/null
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
  for path in /health /presentation.html /demo /onboarding.html /protocol-fields.html /payment-options.html /shopbridge-stack.html /intent-auction-overview.html /architecture.html /registry; do
    curl -fsS "http://127.0.0.1:18099$path" >/dev/null
  done
  cleanup
  trap - EXIT
else
  printf 'docker daemon unavailable; skipping gateway image smoke\n'
fi

section "Verification complete"
