# AgentCart website chart

Serves the static agentcart.eu website from `site/`. The image is unprivileged nginx with the
built site and its configuration baked in, built by `.github/workflows/site-image.yml`. The chart
runs it behind the cluster's HAProxy ingress with cert-manager certificates. It follows the same
pattern as the stadtstack.eu site:
- a restricted pod-security namespace;
- two non-root replicas with a read-only root filesystem;
- default-deny network policies;
- an image pinned by digest.

The site sets no cookies, loads nothing from third parties, and nginx keeps no access logs.

## Values

| Value | Purpose |
|---|---|
| `image.digest` | Required. Reviewed `sha256:` digest of `ghcr.io/giraeffleaeffle/agentcart-site`; tags are never deployed. |
| `hosts.site` | Public hosts (`agentcart.eu`, `www.agentcart.eu`) under one certificate. `www` redirects to the apex. |
| `hosts.preview` | `preview.staging.agentcart.eu`: served with `X-Robots-Tag: noindex, nofollow` under its own certificate. |
| `ingress.haproxySources` | Required. Host-network HAProxy source CIDRs, supplied by the operator at deploy time. They are never committed, and `scripts/check-agentcart-site.sh` rejects private addresses in this repository. |
| `replicas`, `resources` | Defaults: 2 replicas at 25m CPU and 32Mi memory each. |

The image's nginx serves only the three hostnames above, so the schema accepts no others.

## Release

1. Build the image.
   - The Site image workflow publishes `ghcr.io/giraeffleaeffle/agentcart-site@sha256:…` on pushes to `main`; on other branches, run the workflow manually.
   - The GHCR package must be public, because the cluster has no pull secret.
2. Pin that digest in `deploy/agentcart-site/values.yaml`.
3. Apply `deploy/agentcart-site/namespace.yaml`, which sets restricted pod security.
4. Install or upgrade the release:

   ```sh
   helm upgrade --install agentcart-site charts/agentcart-site \
     --namespace agentcart-site \
     --values deploy/agentcart-site/values.yaml \
     --set-json 'ingress.haproxySources=[…reviewed CIDRs…]' \
     --atomic --wait --timeout 10m
   ```

5. Check that the certificate is `Ready`, and that `https://preview.staging.agentcart.eu/` answers 200 with `X-Robots-Tag: noindex, nofollow`.

## Going public

1. In the Hetzner DNS zone `agentcart.eu`:
   - point the `@` and `www` A records at the cluster load balancer (the address that `*.staging` uses);
   - delete their AAAA records, because the cluster ingress has no IPv6;
   - keep the mail records (MX, SPF, DKIM).
2. Wait until both names resolve only to the cluster.
3. Add `hosts.site: [agentcart.eu, www.agentcart.eu]` to `deploy/agentcart-site/values.yaml` and upgrade. cert-manager then issues one certificate for both names over HTTP-01.
4. Check that `https://agentcart.eu/` answers 200 with no `X-Robots-Tag`, and that `https://www.agentcart.eu/` redirects with 301.

Do not add `hosts.site` before step 2. HTTP-01 validation has to reach this cluster; if it runs while DNS still points elsewhere, it fails and cert-manager backs off for hours.

## Rollback

- Use `helm rollback agentcart-site <revision>`.
- To undo the cutover, restore the previous DNS records.
- Leave issued certificates in place: re-issuing counts against Let's Encrypt rate limits.

## Legal and privacy operations

The legal notice and privacy page (`site/src/pages/legal.html`, `privacy.html`) rely on these facts. Re-check them whenever hosting, logging or mail changes.

- **Hosting:** Hetzner Online GmbH, on the Talos cluster in Helsinki (`hel1`).
- **Request logs:** nginx keeps no access logs, and the cluster's HAProxy ingress values configure no syslog endpoint, so no request logs are kept. Revisit the privacy page if either changes.
- **Mail:** `contact@agentcart.eu` runs on an iCloud+ custom email domain since 2026-10-05. Its MX, SPF, DKIM (`sig1._domainkey`) and `apple-domain` verification records are in the `agentcart.eu` zone, and inbound mail was confirmed working.
- **Downloads:** served from GitHub releases. The site links to them and embeds nothing.

Open items:

- **Hetzner data processing agreement (AVV):** conclude it in the Hetzner account at <https://accounts.hetzner.com/account/dpa>, so the privacy page's statement that Hetzner acts as a processor holds.
- **Mail provider:** iCloud+ is a consumer service, and no Art. 28 data processing agreement is known to be available for it, although the privacy page describes the mail provider as a processor. Before using the address for business correspondence such as pilot merchants, move to a mail provider that offers a data processing agreement, or confirm one exists. Then update the privacy page if the provider's role changes.

## Checks

`scripts/check-agentcart-site.sh` runs in `scripts/verify.sh`:
- it builds the site twice and requires identical output;
- it runs `site/check.py`;
- it validates the chart, including the values it must reject;
- it serves the shipped nginx configuration and asserts status codes, security headers, redirects, no-index on the preview host only, and that nginx logs no requests.

The image workflow runs the same HTTP checks against the built image (`--image`).
