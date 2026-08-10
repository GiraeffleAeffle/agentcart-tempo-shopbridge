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
cleanup() { rm -f -- "$rendered"; }
trap cleanup EXIT INT TERM
"$helm_bin" template public-check "$chart" --namespace public-check >"$rendered"

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

if grep -Eq '^kind: Secret$|^stringData:' "$rendered"; then
  printf 'public chart must not render Kubernetes Secret objects\n' >&2
  exit 1
fi
if grep -E '^ *image:' "$rendered" | grep -v '@sha256:' >/dev/null; then
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

rendered_bytes="$(wc -c <"$rendered" | tr -d ' ')"
(( rendered_bytes < 900000 )) || {
  printf 'rendered chart is unexpectedly large: %s bytes\n' "$rendered_bytes" >&2
  exit 1
}

printf 'AgentCart public Helm chart: PASS (%s rendered bytes)\n' "$rendered_bytes"
