#!/usr/bin/env bash
# Validates the agentcart.eu website: deterministic content build, chart invariants, and the
# served behaviour of the site image.
#   scripts/check-agentcart-site.sh                 # verify.sh: all checks; builds site/Dockerfile
#   scripts/check-agentcart-site.sh --image IMAGE   # image workflow: HTTP checks against a built image
set -euo pipefail

root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
chart="$root/charts/agentcart-site"
helm_bin="${HELM:-helm}"
image=""
built_image=""
if [[ "${1:-}" == "--image" ]]; then
  image="${2:?--image needs an image reference}"
fi

work="$(mktemp -d "${TMPDIR:-/tmp}/agentcart-site-check.XXXXXX")"
container=""
cleanup() {
  if [[ -n "$container" ]]; then docker rm -f "$container" >/dev/null 2>&1 || true; fi
  if [[ -n "$built_image" ]]; then docker rmi "$built_image" >/dev/null 2>&1 || true; fi
  rm -rf -- "$work"
}
trap cleanup EXIT INT TERM
fail() { printf 'agentcart site check: %s\n' "$*" >&2; exit 1; }

if [[ -z "$image" ]]; then
  # Content: two builds must be byte-identical and pass the content checker.
  python3 "$root/site/build.py" --out "$work/site" >/dev/null
  python3 "$root/site/build.py" --out "$work/site-again" >/dev/null
  diff -r "$work/site" "$work/site-again" >/dev/null || fail "two builds of the site differ"
  python3 "$root/site/check.py" "$work/site" >/dev/null

  # Chart: valid renders keep the hardened shape; invalid values are rejected.
  command -v "$helm_bin" >/dev/null 2>&1 || fail "Helm is required to validate charts/agentcart-site"
  digest="sha256:$(printf '1%.0s' $(seq 1 64))"
  base=(--namespace agentcart-site --set "image.digest=$digest" --set 'ingress.haproxySources[0]=192.0.2.10/32')
  preview=(--set 'hosts.preview[0]=preview.staging.agentcart.eu')
  public=(--set 'hosts.site[0]=agentcart.eu' --set 'hosts.site[1]=www.agentcart.eu')
  "$helm_bin" lint "$chart" "${base[@]}" "${preview[@]}" >/dev/null
  "$helm_bin" template agentcart-site "$chart" "${base[@]}" "${preview[@]}" >"$work/preview.yaml"
  "$helm_bin" template agentcart-site "$chart" "${base[@]}" "${preview[@]}" "${public[@]}" >"$work/public.yaml"
  [[ "$(grep -c '^kind: Ingress$' "$work/preview.yaml")" == 1 ]] || fail "preview-only render must have exactly one Ingress"
  ! grep -Fq 'host: "agentcart.eu"' "$work/preview.yaml" || fail "public hosts rendered before they were configured"
  [[ "$(grep -c '^kind: Ingress$' "$work/public.yaml")" == 2 ]] || fail "public render must have the site and preview Ingresses"
  grep -A4 'secretName: agentcart-site-tls' "$work/public.yaml" | grep -Fq '"www.agentcart.eu"' || fail "site certificate must cover www"
  for rendered in "$work/preview.yaml" "$work/public.yaml"; do
    for required in 'runAsNonRoot: true' 'readOnlyRootFilesystem: true' 'allowPrivilegeEscalation: false' \
      'drop: [ALL]' 'automountServiceAccountToken: false' 'name: default-deny' 'policyTypes: [Ingress, Egress]' \
      'http-request deny deny_status 405 unless { method GET HEAD }' 'kind: PodDisruptionBudget'; do
      grep -Fq -- "$required" "$rendered" || fail "rendered chart is missing: $required"
    done
    [[ "$(grep -c 'cidr: "192.0.2.10/32"' "$rendered")" == 2 ]] || fail "HAProxy sources must gate the site and the HTTP-01 solver"
    ! grep -Eq '^kind: Secret$' "$rendered" || fail "the site chart must not render Secrets"
    ! grep -E '^ *image:' "$rendered" | grep -v "@$digest" >/dev/null || fail "rendered an image that is not pinned by digest"
  done
  rejected() {
    if "$helm_bin" template agentcart-site "$chart" "$@" >/dev/null 2>&1; then fail "invalid values were accepted: $*"; fi
  }
  rejected --namespace agentcart-site --set 'ingress.haproxySources[0]=192.0.2.10/32' "${preview[@]}"
  rejected --namespace agentcart-site --set image.digest=latest --set 'ingress.haproxySources[0]=192.0.2.10/32'
  rejected --namespace agentcart-site --set "image.digest=$digest" "${preview[@]}"
  rejected "${base[@]}" --set 'ingress.haproxySources[0]=not-a-cidr'
  rejected "${base[@]}" --set 'hosts.site[0]=example.com'
  rejected "${base[@]}" --set 'hosts.preview[0]=agentcart.eu'
  rejected "${base[@]}" --set replicas=0

  # Public repository: no private deployment indicators.
  for forbidden in '/Users/' '.secrets/' '10.255.' '10.42.' '10.244.' '77.42.11.9' '167.233.116.149' \
    'wireguard-daily' 'talosconfig' 'age.key'; do
    if grep -R -Fq -- "$forbidden" "$root/site" "$chart" "$root/deploy/agentcart-site" 2>/dev/null; then
      fail "private deployment indicator found in the website sources: $forbidden"
    fi
  done

  # Serve the real image built from site/Dockerfile (no bind mounts: Docker hosts such as
  # Colima share only parts of the host filesystem).
  built_image="agentcart-site:check-$$"
  docker build --quiet --tag "$built_image" "$root/site" >/dev/null
  image="$built_image"
fi
container="$(docker run -d --read-only --tmpfs /tmp --user 101 -p 127.0.0.1::8080 "$image")"

port="$(docker port "$container" 8080/tcp | awk -F: 'NR == 1 {print $NF}')"
for _ in $(seq 1 50); do
  curl -sf -o /dev/null "http://127.0.0.1:$port/healthz" && break
  sleep 0.2
done

expect() {
  local host="$1" path="$2" want="$3" status pattern
  shift 3
  status="$(curl -s -o "$work/body" -D "$work/headers" -w '%{http_code}' -H "Host: $host" "http://127.0.0.1:$port$path")"
  [[ "$status" == "$want" ]] || fail "$host$path answered $status, expected $want"
  for pattern in "$@"; do
    tr -d '\r' <"$work/headers" | grep -Eiq -- "$pattern" || fail "$host$path is missing a header matching: $pattern"
  done
}
csp="^content-security-policy: default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'$"

expect agentcart.eu / 200 "$csp" '^strict-transport-security: max-age=31536000$' '^x-content-type-options: nosniff$' \
  '^referrer-policy: no-referrer$' '^content-type: text/html'
! grep -qi '^x-robots-tag' "$work/headers" || fail "the public site must stay indexable"
grep -Fq '<html lang="en">' "$work/body" || fail "home page is not the built site"
for path in /merchants/ /agents/ /legal/ /privacy/ /robots.txt /sitemap.xml; do
  expect agentcart.eu "$path" 200 "$csp"
done
expect agentcart.eu /assets/site.css 200 '^content-type: text/css' '^cache-control: max-age=3600$'
expect agentcart.eu /merchants 301 '^location: /merchants/$'
expect agentcart.eu /no-such-page/ 404 "$csp"
if [[ -n "$built_image" ]]; then
  cmp -s "$work/body" "$work/site/404.html" || fail "missing pages must answer with the built 404 page"
fi
expect agentcart.eu /404.html 404
expect www.agentcart.eu '/agents/?ref=docs' 301 '^location: https://agentcart\.eu/agents/\?ref=docs$' "$csp"
expect preview.staging.agentcart.eu / 200 '^x-robots-tag: noindex, nofollow$' "$csp"
expect unknown.example / 404
expect unknown.example /healthz 200

# No request is ever logged, so client addresses never reach the container logs.
logs="$(docker logs "$container" 2>&1)"
for leaked in 'GET /' '172.17.' '127.0.0.1' 'curl/'; do
  ! grep -Fq -- "$leaked" <<<"$logs" || fail "nginx logs contain request data: $leaked"
done

printf 'AgentCart website: PASS (%s)\n' "${image:-sources}"
