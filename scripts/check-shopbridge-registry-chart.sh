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
grep -Fq '"status": "not_deployed"' "$rendered"
grep -Fq 'woocommerce-demo-shop-eur' "$rendered"
grep -Fq 'woocommerce-demo-shop-usd' "$rendered"

if grep -Eq '^[[:space:]]+- path: /v2/?$' "$rendered"; then
  printf 'ShopBridge registry chart must not claim the OCI /v2 path\n' >&2
  exit 1
fi

printf 'AgentCart ShopBridge registry chart: PASS\n'
