#!/usr/bin/env bash
set -euo pipefail

root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:-sync}"
[[ "$mode" == sync || "$mode" == --check ]] || {
  printf 'usage: %s [--check]\n' "$0" >&2
  exit 2
}

sources=(
  woocommerce-shopbridge/agentcart-shopbridge/agentcart-shopbridge.php
  woocommerce-shopbridge/agentcart-shopbridge/readme.txt
  woocommerce-shopbridge/agentcart-shopbridge/uninstall.php
  woocommerce-shopbridge/agentcart-shopbridge/includes/class-agentcart-shopbridge-discovery-facets.php
  woocommerce-shopbridge/agentcart-shopbridge/includes/class-agentcart-shopbridge-onchain-identity.php
  woocommerce-shopbridge/agentcart-shopbridge/includes/class-agentcart-shopbridge-registry-archive.php
  woocommerce-shopbridge/agentcart-shopbridge/includes/class-agentcart-shopbridge-registry-events.php
  woocommerce-shopbridge/agentcart-shopbridge/includes/class-agentcart-shopbridge-registry-rpc.php
  woocommerce-shopbridge/agentcart-shopbridge/includes/class-agentcart-shopbridge-registry-readiness.php
  woocommerce-shopbridge/agentcart-shopbridge/includes/trait-agentcart-shopbridge-verifier-client.php
  demo/woocommerce/seed-products.sh
  gateway/scripts/onchain-registry-indexer.mjs
  gateway/scripts/onchain-registry-indexer-loop.mjs
)
destinations=(
  charts/agentcart-shopbridge/files/plugin/agentcart-shopbridge.php
  charts/agentcart-shopbridge/files/plugin/readme.txt
  charts/agentcart-shopbridge/files/plugin/uninstall.php
  charts/agentcart-shopbridge/files/plugin/includes/class-agentcart-shopbridge-discovery-facets.php
  charts/agentcart-shopbridge/files/plugin/includes/class-agentcart-shopbridge-onchain-identity.php
  charts/agentcart-shopbridge/files/plugin/includes/class-agentcart-shopbridge-registry-archive.php
  charts/agentcart-shopbridge/files/plugin/includes/class-agentcart-shopbridge-registry-events.php
  charts/agentcart-shopbridge/files/plugin/includes/class-agentcart-shopbridge-registry-rpc.php
  charts/agentcart-shopbridge/files/plugin/includes/class-agentcart-shopbridge-registry-readiness.php
  charts/agentcart-shopbridge/files/plugin/includes/trait-agentcart-shopbridge-verifier-client.php
  charts/agentcart-shopbridge/files/bootstrap/seed-products.sh
  charts/agentcart-shopbridge-registry/files/indexer/onchain-registry-indexer.mjs
  charts/agentcart-shopbridge-registry/files/indexer/onchain-registry-indexer-loop.mjs
)

stale=0
for index in "${!sources[@]}"; do
  source_file="$root/${sources[$index]}"
  destination_file="$root/${destinations[$index]}"
  if [[ "$mode" == --check ]]; then
    if ! cmp -s "$source_file" "$destination_file"; then
      printf 'stale Helm chart copy: %s\n' "${destinations[$index]}" >&2
      stale=1
    fi
  else
    mkdir -p "$(dirname -- "$destination_file")"
    install -m 0644 "$source_file" "$destination_file"
  fi
done

(( stale == 0 )) || exit 1
