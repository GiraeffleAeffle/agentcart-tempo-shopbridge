#!/usr/bin/env bash
set -euo pipefail

root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
chart="$root/charts/agentcart-shopbridge-registry"
helm_bin="${HELM:-helm}"

command -v "$helm_bin" >/dev/null 2>&1 || {
  printf 'Helm is required to validate the ShopBridge registry chart\n' >&2
  exit 1
}

"$helm_bin" lint "$chart" >/dev/null
"$helm_bin" lint "$chart" --values "$chart/values.pilot.yaml" >/dev/null

rendered="$(mktemp "${TMPDIR:-/tmp}/agentcart-registry-helm.XXXXXX")"
cleanup() { rm -f -- "$rendered"; }
trap cleanup EXIT INT TERM
"$helm_bin" template registry-check "$chart" --namespace registry-check >"$rendered"
"$helm_bin" template registry-pilot "$chart" --namespace registry-check \
  --values "$chart/values.pilot.yaml" >>"$rendered"
"$helm_bin" template registry-onchain "$chart" --namespace registry-check \
  --set registry.onchainEvents.enabled=true \
  --set registry.onchainEvents.source=static \
  --set-json 'registry.onchainRecords=[{"recordHash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","document":{"registry_record":{"merchant_id":"immutable-test"}}}]' \
  --set-json 'registry.onchainEvents.document={"schema":"agentcart.onchain_registry_contract_events.v1","implementation":"agentcart.onchain_registry_rpc_indexer.v1","chain_id":"eip155:42431","registry_address":"0x1111111111111111111111111111111111111111","finality":{"block_tag":"finalized","block_number":10,"block_hash":"0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","indexed_from_block":1,"indexed_to_block":10},"indexed_at":"2026-08-13T00:00:00Z","complete":true,"errors":[],"events":[]}' \
  >>"$rendered"
"$helm_bin" template registry-rpc-indexer "$chart" --namespace registry-check \
  --set registry.onchainEvents.enabled=true \
  --set registry.onchainEvents.source=rpc_indexer \
  --set registry.onchainEvents.rpcIndexer.rpcUrl=https://rpc.example.test \
  --set-string registry.onchainEvents.rpcIndexer.fromBlock=100 \
  --set registry.onchainEvents.rpcIndexer.image.digest=sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc \
  --set registry.onchain.tempo.status=testnet_only \
  --set-string registry.onchain.tempo.chainId=42431 \
  --set registry.onchain.tempo.contractAddress=0x1111111111111111111111111111111111111111 \
  --set registry.onchain.tempo.explorerUrl=https://explorer.example.test/address/0x1111111111111111111111111111111111111111 \
  >>"$rendered"

if grep -Eq '^kind: Secret$|^stringData:' "$rendered"; then
  printf 'registry chart must not render Kubernetes Secret objects\n' >&2
  exit 1
fi
if grep -E '^ *image:' "$rendered" | grep -v '@sha256:' >/dev/null; then
  printf 'registry chart rendered an unpinned container image\n' >&2
  exit 1
fi

grep -Fq 'automountServiceAccountToken: false' "$rendered"
grep -Fq 'readOnlyRootFilesystem: true' "$rendered"
grep -Fq 'http-request deny deny_status 405 unless { method GET HEAD }' "$rendered"
grep -Fq 'path: /v1/registry' "$rendered"
grep -Fq 'pathType: Exact' "$rendered"
grep -Fq 'agentcart.hosted_merchant_registry_feed.v1' "$rendered"
grep -Fq 'agentcart.onchain_registry_rpc_indexer.v1' "$rendered"
grep -Fq '"onchain_events_url": "https://registry.example.test/v1/registry/onchain/events"' "$rendered"
grep -Fq 'location = /v1/registry/onchain/events' "$rendered"
grep -Fq 'alias /var/run/agentcart-registry/onchain-events.json' "$rendered"
grep -Fq 'name: finalized-registry-indexer' "$rendered"
grep -Fq 'command: [node, /app/indexer/onchain-registry-indexer-loop.mjs]' "$rendered"
grep -Fq 'value: "https://rpc.example.test"' "$rendered"
grep -Fq 'value: "0x1111111111111111111111111111111111111111"' "$rendered"
grep -Fq 'value: "42431"' "$rendered"
grep -Fq 'path: /v1/registry/onchain/events' "$rendered"
grep -Fq 'cidr: 0.0.0.0/0' "$rendered"
grep -Fq 'cidr: ::/0' "$rendered"
grep -Fq 'onchain-registry-indexer-loop.mjs' "$rendered"
grep -Fq 'location = /v1/registry/onchain/records/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' "$rendered"
grep -Fq 'Cache-Control "public, max-age=31536000, immutable"' "$rendered"
grep -Fq '"merchant_id": "immutable-test"' "$rendered"
grep -Fq '"status": "not_deployed"' "$rendered"
grep -Fq 'woocommerce-demo-shop-eur' "$rendered"
grep -Fq 'woocommerce-demo-shop-usd' "$rendered"

if "$helm_bin" lint "$chart" \
  --set registry.onchain.tempo.status=testnet_only \
  --set registry.onchain.tempo.chainId=42431 >/dev/null 2>&1; then
  printf 'registry chart accepted an incomplete Tempo deployment identity\n' >&2
  exit 1
fi

if "$helm_bin" lint "$chart" \
  --set registry.onchainEvents.enabled=true \
  --set registry.onchainEvents.source=rpc_indexer \
  --set registry.onchainEvents.rpcIndexer.rpcUrl=https://rpc.example.test \
  --set registry.onchain.tempo.status=testnet_only \
  --set-string registry.onchain.tempo.chainId=42431 \
  --set registry.onchain.tempo.contractAddress=0x1111111111111111111111111111111111111111 \
  --set registry.onchain.tempo.explorerUrl=https://explorer.example.test/address/0x1111111111111111111111111111111111111111 \
  >/dev/null 2>&1; then
  printf 'registry chart accepted an unpinned recurring indexer image\n' >&2
  exit 1
fi

if "$helm_bin" template registry-invalid-indexer "$chart" \
  --set registry.onchainEvents.enabled=true \
  --set registry.onchainEvents.source=rpc_indexer \
  --set registry.onchainEvents.rpcIndexer.rpcUrl=https://rpc.example.test \
  --set registry.onchainEvents.rpcIndexer.image.digest=sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc \
  >/dev/null 2>&1; then
  printf 'registry chart accepted an indexer for an undeployed registry\n' >&2
  exit 1
fi

if grep -Eq '^[[:space:]]+- path: /v2/?$' "$rendered"; then
  printf 'ShopBridge registry chart must not claim the OCI /v2 path\n' >&2
  exit 1
fi

printf 'AgentCart ShopBridge registry chart: PASS\n'
