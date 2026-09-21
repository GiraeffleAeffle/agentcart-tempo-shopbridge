#!/usr/bin/env bash
# Disposable CI fixture only; all provider calls are intercepted by the PHP harness.
set -euo pipefail
[[ "${CI:-}" == true ]] || { printf 'Run the existing-shop harness locally; this setup is CI-only.\n' >&2; exit 2; }
root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Do not inherit merchant/provider credentials into the synthetic fixture.
for key in $(env | cut -d= -f1); do
  case "$key" in AGENTCART_*|WORDPRESS_*|WOO_*) unset "$key" ;; esac
done
export WOO_HOST_PORT=18097 WOO_PUBLIC_URL=http://127.0.0.1:18097
project=shopbridge-recovery-ci
compose=(docker compose -p "$project" -f "$root/demo/woocommerce/docker-compose.yml")
cleanup() { "${compose[@]}" down >/dev/null 2>&1 || true; }
trap cleanup EXIT
"${compose[@]}" up -d db wordpress
for attempt in $(seq 1 30); do
  if "${compose[@]}" exec -T db mariadb-admin ping -uroot -pwordpress-root --silent >/dev/null 2>&1; then break; fi
  sleep 2
done
"${compose[@]}" run --rm wpcli
wp() { "${compose[@]}" run --rm --no-deps --entrypoint wp wpcli "$@" --allow-root; }
wp config set AGENTCART_PAYMENT_VERIFIER_URL https://verifier.example.com/verify
wp config set AGENTCART_ALLOW_PRIVATE_PAYMENT_VERIFIER_URL true --raw
wp wc hpos sync
wp option update woocommerce_custom_orders_table_enabled no
python3 "$root/scripts/check-woocommerce-checkout-recovery.py" --project "$project"
wp wc hpos sync
wp option update woocommerce_custom_orders_table_enabled yes
python3 "$root/scripts/check-woocommerce-checkout-recovery.py" --project "$project"
