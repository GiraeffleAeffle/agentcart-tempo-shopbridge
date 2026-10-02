#!/usr/bin/env bash
# All traffic stays on an isolated Docker network (also works on colima without port forwarding).
# The test-only signing bridge uses the verifier image's Node 22 + viem directly;
# its runtime-generated ephemeral account stays in memory and is never logged.
set -euo pipefail
root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Do not inherit merchant credentials or local compose .env files.
for key in $(env | cut -d= -f1); do
  case "$key" in AGENTCART_*|WORDPRESS_*|WOO_*) unset "$key" ;; esac
done
cache="${XDG_CACHE_HOME:-$HOME/.cache}"
mkdir -p "$cache"
export X402_E2E_TMP
X402_E2E_TMP="$(mktemp -d "$cache/shopbridge-x402-e2e.XXXXXXXX")"
run_id="$(basename "$X402_E2E_TMP" | tr '[:upper:].' '[:lower:]-')"
project="$run_id"
export X402_E2E_IMAGE="shopbridge-x402-e2e:$run_id"
compose=(docker compose --env-file /dev/null -p "$project" -f "$root/demo/woocommerce/docker-compose.yml" -f "$root/demo/woocommerce/x402-e2e/compose.yml")
wp() { "${compose[@]}" run --rm -T --no-deps --entrypoint wp wpcli "$@" --allow-root; }
restore_timeout=0
cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if [[ "$restore_timeout" == 1 ]]; then wp option delete agentcart_shopbridge_x402_max_timeout_seconds >/dev/null 2>&1 || true; fi
  "${compose[@]}" --profile e2e down -v --remove-orphans >/dev/null 2>&1 || true
  docker image rm "$X402_E2E_IMAGE" >/dev/null 2>&1 || true
  rm -rf "$X402_E2E_TMP"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir "$X402_E2E_TMP/work"
# The token file must be readable by the containers' unprivileged users, but its parent is 0700.
openssl rand -hex 32 > "$X402_E2E_TMP/verifier-token"
chmod 644 "$X402_E2E_TMP/verifier-token"
# Installation may fetch dependencies; payment scenarios themselves never leave the fake stack.
# Match the existing Plugin Check installer; the base compose binds this gitignored archive.
WOO_ZIP="$root/demo/woocommerce/woocommerce.latest-stable.zip"
if [ ! -f "$WOO_ZIP" ]; then
  printf 'Downloading WooCommerce plugin archive...\n' >&2
  curl -fL --retry 5 --retry-delay 2 --connect-timeout 30 \
    -o "$WOO_ZIP" \
    https://downloads.wordpress.org/plugin/woocommerce.latest-stable.zip >&2
fi
docker build -f "$root/gateway/Dockerfile.verifier" -t "$X402_E2E_IMAGE" "$root/gateway" >&2
"${compose[@]}" up -d db wordpress verifier signer >&2
for attempt in $(seq 1 60); do
  if "${compose[@]}" exec -T db mariadb-admin ping -uroot -pwordpress-root --silent >/dev/null 2>&1; then break; fi
  sleep 2
done
"${compose[@]}" run --rm -T wpcli >&2
wp option update agentcart_shopbridge_x402_network eip155:84532 >&2
wp option update agentcart_shopbridge_x402_asset 0x036CbD53842c5426634e7929541eC2318f3dCF7e >&2
wp option update agentcart_shopbridge_x402_pay_to 0x2222222222222222222222222222222222222222 >&2
wp eval '$m = new ReflectionMethod("AgentCart_ShopBridge", "check_verifier_capabilities"); $m->setAccessible(true); $result = $m->invoke(null); $s = get_option("agentcart_shopbridge_verifier_capabilities"); if ($result !== "Verifier x402 capabilities confirmed." || ($s["ok"] ?? null) !== true || ($s["x402"]["configured"] ?? null) !== true || ($s["x402"]["facilitator"]["supported_kind_confirmed"] ?? null) !== true) { fwrite(STDERR, json_encode([$result, $s])); exit(1); } echo "x402 capabilities confirmed\n";' >&2
# Look up the seeded tea SKU rather than depending on auto-increment ids.
wp eval '$products = wc_get_products(["limit" => -1]); $found = false; foreach ($products as $p) { if (stripos($p->get_name(), "tea") !== false) { wc_update_product_stock($p, 100); $found = true; } } if (!$found) { exit(1); }' >&2
run_case() { "${compose[@]}" run --rm -T --no-deps skill python /e2e/drive_x402.py "$1"; }
assert_events() {
  "${compose[@]}" logs --no-color --no-log-prefix verifier > "$X402_E2E_TMP/work/verifier.log"
  "${compose[@]}" run --rm -T --no-deps skill python /e2e/assert_events.py "$1" "$2" >&2
}
run_case available > "$X402_E2E_TMP/work/available.json"
assert_events 0 0
run_case positive > "$X402_E2E_TMP/work/positive-result.json"
assert_events 1 0
run_case replay > "$X402_E2E_TMP/work/replay.json"
assert_events 1 0
for case in N1 N2 N3; do
  run_case "$case" > "$X402_E2E_TMP/work/$case.json"
  if [[ "$case" == N3 ]]; then assert_events 1 1; else assert_events 1 0; fi
done
wp eval 'if (get_option("agentcart_shopbridge_x402_max_timeout_seconds", false) !== false) { fwrite(STDERR, "Expected the isolated seed timeout option to be unset\n"); exit(1); }' >&2
restore_timeout=1
wp option update agentcart_shopbridge_x402_max_timeout_seconds 600 >&2
run_case N4 > "$X402_E2E_TMP/work/N4.json"
wp option delete agentcart_shopbridge_x402_max_timeout_seconds >&2
restore_timeout=0
run_case available > "$X402_E2E_TMP/work/restored.json"
assert_events 1 1
"${compose[@]}" run --rm -T --no-deps skill python /e2e/summary.py "$project" "$X402_E2E_IMAGE"
