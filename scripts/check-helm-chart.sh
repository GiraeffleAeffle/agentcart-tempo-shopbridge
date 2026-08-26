#!/usr/bin/env bash
set -euo pipefail

root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
chart="$root/charts/agentcart-shopbridge"
helm_bin="${HELM:-helm}"

command -v "$helm_bin" >/dev/null 2>&1 || {
  printf 'Helm is required to validate the public chart\n' >&2
  exit 1
}

bash "$root/scripts/sync-helm-chart-files.sh" --check
"$helm_bin" lint "$chart" >/dev/null

rendered="$(mktemp "${TMPDIR:-/tmp}/agentcart-helm.XXXXXX")"
rendered_verifier="$(mktemp "${TMPDIR:-/tmp}/agentcart-helm-verifier.XXXXXX")"
cleanup() { rm -f -- "$rendered" "$rendered_verifier"; }
trap cleanup EXIT INT TERM
"$helm_bin" template public-check "$chart" --namespace public-check >"$rendered"
"$helm_bin" template verifier-check "$chart" --namespace verifier-check \
  --set store.checkoutMode=external_verifier_only \
  --set store.signedRequestMode=require_mutations \
  --set verifier.enabled=true \
  --set verifier.alerts.enabled=true \
  --set 'verifier.enabledRails[0]=tempo-mpp' \
  --set 'verifier.enabledRails[1]=stripe-card-mpp' \
  --set verifier.tempo.settlementMode=verify \
  --set images.verifier.digest=sha256:1111111111111111111111111111111111111111111111111111111111111111 \
  --set store.registryOnchain.controller=0x1111111111111111111111111111111111111111 \
  --set store.registryOnchain.chainId=eip155:42431 \
  --set store.registryOnchain.registryAddress=0x2222222222222222222222222222222222222222 \
  --set store.registryOnchain.recordId=0x3333333333333333333333333333333333333333333333333333333333333333 \
  >"$rendered_verifier"

if "$helm_bin" lint "$chart" \
  --set store.checkoutMode=external_verifier_only \
  --set store.signedRequestMode=require_mutations \
  --set verifier.enabled=true \
  --set images.verifier.digest=sha256:1111111111111111111111111111111111111111111111111111111111111111 \
  >/dev/null 2>&1; then
  printf 'Tempo verifier without settlement verification unexpectedly passed chart validation\n' >&2
  exit 1
fi

if "$helm_bin" lint "$chart" \
  --set store.registryOnchain.recordId=0x3333333333333333333333333333333333333333333333333333333333333333 \
  >/dev/null 2>&1; then
  printf 'partial onchain registry identity unexpectedly passed chart validation\n' >&2
  exit 1
fi

if "$helm_bin" lint "$chart" \
  --set verifier.alerts.minSeverity=noisy \
  >/dev/null 2>&1; then
  printf 'invalid verifier alert severity unexpectedly passed chart validation\n' >&2
  exit 1
fi

for forbidden in \
  '/Users/' \
  '.secrets/' \
  '10.255.' \
  '10.42.' \
  '10.244.' \
  '77.42.11.9' \
  '167.233.116.149' \
  'wireguard-daily' \
  'talosconfig' \
  'age.key' \
  'CURRENT_BOOTSTRAP_BUNDLE' \
  'MIGRATION_RECEIPT' \
  'incident-2026'; do
  if grep -R -Fq "$forbidden" "$chart" 2>/dev/null; then
    printf 'private deployment indicator found in public chart: %s\n' "$forbidden" >&2
    exit 1
  fi
done

if find "$chart" -type f -perm -002 | grep -q .; then
  printf 'public chart contains a world-writable file\n' >&2
  exit 1
fi

if grep -Eq '^kind: Secret$|^stringData:' "$rendered" "$rendered_verifier"; then
  printf 'public chart must not render Kubernetes Secret objects\n' >&2
  exit 1
fi
if grep -E '^ *image:' "$rendered" "$rendered_verifier" | grep -v '@sha256:' >/dev/null; then
  printf 'public chart rendered an unpinned container image\n' >&2
  exit 1
fi

grep -Fq 'path_beg /wp-admin' "$rendered"
grep -Fq 'path /wp-login.php' "$rendered"
grep -Fq 'path /xmlrpc.php' "$rendered"
grep -Fq 'path_beg /wp-json/wp/v2/users' "$rendered"
grep -Fq 'location = /.well-known/agentcart.json' "$rendered"
grep -Fq 'automountServiceAccountToken: false' "$rendered"
grep -Fq 'AGENTCART_REQUIRE_DEPLOYMENT_SECRETS' "$rendered"
grep -Fq 'AGENTCART_SUPPRESS_DEMO_CREDENTIAL_ECHO' "$rendered"
grep -Fq 'class-agentcart-shopbridge-onchain-identity.php' "$rendered"
grep -Fq 'class-agentcart-shopbridge-registry-archive.php' "$rendered"
grep -Fq 'class-agentcart-shopbridge-registry-events.php' "$rendered"
grep -Fq 'class-agentcart-shopbridge-registry-rpc.php' "$rendered"
grep -Fq 'class-agentcart-shopbridge-registry-readiness.php' "$rendered"
if grep -Fq 'AGENTCART_VERIFIER_ALERT_WEBHOOK_URL' "$rendered"; then
  printf 'disabled verifier alerts unexpectedly rendered a Secret reference\n' >&2
  exit 1
fi

grep -Fq 'AGENTCART_VERIFIER_REPLAY_STORE_DRIVER' "$rendered_verifier"
grep -Fq 'AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY' "$rendered_verifier"
grep -Fq 'AGENTCART_VERIFIER_REQUIRE_REPLAY_JOURNAL' "$rendered_verifier"
grep -Fq 'AGENTCART_PAYMENT_VERIFIER_TOKEN' "$rendered_verifier"
grep -Fq 'AGENTCART_VERIFIER_ALERT_WEBHOOK_URL' "$rendered_verifier"
grep -Fq 'AGENTCART_VERIFIER_ALERT_WEBHOOK_TOKEN' "$rendered_verifier"
grep -Fq 'AGENTCART_VERIFIER_ALERT_MIN_SEVERITY' "$rendered_verifier"
grep -Fq 'AGENTCART_VERIFIER_ALERT_THROTTLE_SECONDS' "$rendered_verifier"
grep -Fq 'STRIPE_SANDBOX_SECRET_KEY' "$rendered_verifier"
grep -Fq 'STRIPE_PROFILE_ID' "$rendered_verifier"
grep -Fq 'MPP_SECRET_KEY' "$rendered_verifier"
grep -Fq 'external_verifier_only' "$rendered_verifier"
grep -Fq 'pinned_internal' "$rendered_verifier"
grep -Fq 'kind: PersistentVolumeClaim' "$rendered_verifier"
grep -Fq 'app.kubernetes.io/component: verifier' "$rendered_verifier"
grep -Fq 'AGENTCART_REGISTRY_ONCHAIN_CONTROLLER' "$rendered_verifier"
grep -Fq 'eip155:42431' "$rendered_verifier"

rendered_bytes="$(wc -c <"$rendered" | tr -d ' ')"
(( rendered_bytes < 900000 )) || {
  printf 'rendered chart is unexpectedly large: %s bytes\n' "$rendered_bytes" >&2
  exit 1
}

printf 'AgentCart public Helm chart: PASS (%s rendered bytes)\n' "$rendered_bytes"
