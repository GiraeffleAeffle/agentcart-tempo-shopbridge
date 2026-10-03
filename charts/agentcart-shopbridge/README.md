# AgentCart ShopBridge Helm chart

This chart deploys one clean WordPress, WooCommerce, and AgentCart ShopBridge
store. Install it once per storefront so every release has an independent
database, uploads volume, hostname, TLS certificate, and Secret.

The chart is intentionally environment-neutral. It contains no Kubernetes
Secret object, cloud credentials, cluster endpoints, private CIDRs, or incident
artifacts. Image references use immutable digests, application code is rebuilt
from checksum-verified public archives on every pod start, and database/uploads
claims are retained.

## Requirements

- Kubernetes 1.27 or newer;
- Helm 3;
- HAProxy Kubernetes Ingress Controller;
- cert-manager when `certificate.create=true`;
- a default StorageClass, or explicit storage classes in private values;
- one pre-provisioned Kubernetes Secret per release.

The public admin-route controls are verified only with HAProxy Ingress. The
values schema rejects other ingress classes because silently publishing
`/wp-admin`, `/wp-login.php`, XML-RPC, or the WordPress users API is unsafe.

## Secret contract

Provision the Secret outside Helm using External Secrets, SOPS, or a local
mode-0600 environment file. Do not pass credentials through `--set`, commit a
Secret manifest, or put secret values in a Helm values file.

The Secret named by `existingSecret` must contain:

```text
WORDPRESS_DB_PASSWORD
MARIADB_ROOT_PASSWORD
WOO_ADMIN_USER
WOO_ADMIN_PASSWORD
WOO_ADMIN_EMAIL
AGENTCART_SHOPBRIDGE_TOKEN
AGENTCART_SIGNED_REQUEST_SECRET
WORDPRESS_AUTH_KEY
WORDPRESS_SECURE_AUTH_KEY
WORDPRESS_LOGGED_IN_KEY
WORDPRESS_NONCE_KEY
WORDPRESS_AUTH_SALT
WORDPRESS_SECURE_AUTH_SALT
WORDPRESS_LOGGED_IN_SALT
WORDPRESS_NONCE_SALT
```

When `verifier.enabled=true`, it must additionally contain:

```text
AGENTCART_PAYMENT_VERIFIER_TOKEN
```

When `verifier.alerts.enabled=true`, the Secret must also contain the receiver
URL and may contain a Bearer token:

```text
AGENTCART_VERIFIER_ALERT_WEBHOOK_URL
AGENTCART_VERIFIER_ALERT_WEBHOOK_TOKEN  # optional
```

Keep the URL in the Secret because webhook paths or query parameters may carry
receiver credentials. `verifier.alerts.minSeverity` and
`verifier.alerts.throttleSeconds` are non-secret policy values.

When `verifier.enabledRails` includes `stripe-card-mpp`, it must also contain:

```text
STRIPE_SANDBOX_SECRET_KEY
STRIPE_PROFILE_ID
MPP_SECRET_KEY
```

When `verifier.tempo.refundMode=live`, it must also contain the dedicated
testnet refund signer:

```text
AGENTCART_TEMPO_REFUND_PRIVATE_KEY
```

Do not reuse a deployer, registry controller, merchant treasury, or mainnet key
as the refund signer. Give the pilot signer only the testnet balance required
for bounded refund drills.

For a local private file that already contains those keys:

```sh
kubectl -n shopbridge create secret generic example-shopbridge-secrets \
  --from-env-file=/secure/path/example-shopbridge.env
```

## Install

Copy the non-secret example to the ignored private filename and edit only
environment-specific values:

```sh
cp charts/agentcart-shopbridge/values.example.yaml \
  charts/agentcart-shopbridge/values.private.yaml
chmod 600 charts/agentcart-shopbridge/values.private.yaml

helm upgrade --install example-shop charts/agentcart-shopbridge \
  --namespace shopbridge \
  --create-namespace \
  --values charts/agentcart-shopbridge/values.private.yaml
```

Use a separate release, values file, Secret, and merchant ID for every store.
Real ingress source CIDRs belong only in the ignored private values file.

## External verifier pilot profile

The verifier is disabled by default. Enabling it creates a single-replica,
non-root verifier Deployment, a retained SQLite PVC, a cluster-local Service,
and narrowly scoped NetworkPolicy rules. The storefront is then pinned to the
cluster-local verifier and receives its verifier credential only from the
pre-provisioned Secret.

Build and publish `gateway/Dockerfile.verifier`, resolve the registry digest,
and put that immutable digest in the ignored private values file. A pilot that
accepts Tempo payments and performs real testnet refunds uses non-secret values
like these:

```yaml
images:
  verifier:
    repository: registry.example.test/agentcart/shopbridge-verifier
    digest: sha256:REPLACE_WITH_64_HEX_DIGEST

store:
  marketProfile: usd
  checkoutMode: external_verifier_only
  signedRequestMode: require_mutations

verifier:
  enabled: true
  enabledRails: [tempo-mpp]
  alerts:
    enabled: true
    minSeverity: warning
    throttleSeconds: 300
  tempo:
    settlementMode: verify
    settlementRpcUrl: https://REPLACE_WITH_TESTNET_RPC
    refundMode: live
    refundRpcUrl: https://REPLACE_WITH_TESTNET_RPC
```

The values schema rejects a verifier-enabled release unless checkout is
verifier-only and mutation endpoints require signed requests. A release that
enables `tempo-mpp` must also set settlement verification to `verify`; this
prevents a healthy-looking deployment that can parse a proof but cannot verify
the transfer onchain. Keep the replay driver, durable replay requirement, and
append-only journal enabled; the retained PVC is the recovery boundary for
payment-proof replay state.

The default EUR market profile is sandbox/demo only: its disabled verifier
does not claim real settlement. For real Tempo settlement, use `marketProfile:
usd` as above. pathUSD and USDC.e are USD-denominated; EUR quotes are rejected
with `tempo_settlement_currency_mismatch`. No quote-bound FX contract is
implemented. An EUR store needs a configured Stripe/card rail instead.
The chart schema rejects an enabled Tempo-only verifier with `marketProfile:
eur`. EUR with both Tempo and Stripe/card enabled remains valid: Stripe handles
EUR quotes while Tempo is unavailable for them at runtime.

With alerts enabled, rejected and failed verifier operations are POSTed to the
Secret-backed receiver. A rollout is not alert-ready until a deliberate
warning is accepted by that receiver and the verifier records delivery state
`sent`; log generation or `state=skipped` is not delivery evidence.

### x402 Base Sepolia settlement

The verifier image includes `gateway/scripts/verifier-x402.mjs`. To enable the
testnet-only x402 v2 `exact` USDC rail, set `verifier.enabled=true`,
`verifier.enabledRails: [x402-compatible]`, and `verifier.x402.mode=settle`. Keep checkout
verifier-only and signed mutations required as above. The schema requires
settlement mode for an enabled x402 rail; the chart mounts the SQLite replay
store at `/data/replay-store.sqlite`. Do not replace it with an ephemeral store.

```yaml
verifier:
  enabled: true
  enabledRails: [x402-compatible]
  x402:
    mode: settle
    network: "eip155:84532"
    facilitatorUrl: "https://x402.org/facilitator"
    rpcUrl: "https://sepolia.base.org"
    confirmations: 1
    facilitatorTimeoutMs: 7000
```

`verifier.x402.mode` defaults to `disabled`; the other values above are defaults.
The facilitator settle timeout must be 100–7000 ms. Verify has a 2500 ms
ceiling, settle defaults to 7000 ms, and confirmation has a 1500 ms total
ceiling. RPC calls are capped at 1500 ms and the remaining 12000 ms global
budget (below the plugin's 15 s timeout). Ambiguous submission always reconciles.
URLs must use HTTPS and resolve exclusively to global addresses; redirects
fail closed. The chart deliberately does not expose
the local-test-only `AGENTCART_X402_ALLOW_PRIVATE_URLS=true` override.
Authenticated operations cache facilitator `/supported` capabilities for ten
minutes; health checks make no facilitator or RPC calls. x402 refunds are
unsupported. See `docs/VERIFIER_CONTRACT.md` and
`docs/VERIFIER_OPERATIONS_READINESS.md` for durable retry handling.

For a slow private registry tunnel, use
`scripts/push-oci-layout-resumable.py` against a loopback port-forward. It
verifies the OCI manifest and every blob locally, uploads in bounded resumable
PATCH chunks, publishes the tag last, and verifies the registry's final
manifest digest. This avoids relying on a single long-lived layer request.

## Security behavior

- no service-account token is mounted;
- containers run without privilege escalation and drop all capabilities;
- WordPress runs with a read-only root filesystem;
- the application container never receives the MariaDB root password;
- public WordPress administration, login, XML-RPC, and user enumeration are
  denied at HAProxy Ingress;
- ShopBridge's four exact `/.well-known/` JSON documents remain public;
- default-deny NetworkPolicies isolate storefront and database pods;
- the optional verifier accepts traffic only from its own storefront and may
  egress only to DNS and public HTTPS RPC endpoints;
- egress to private, loopback, link-local, and carrier-grade NAT ranges is
  denied for public HTTPS calls;
- persistent claims survive Helm uninstall and StatefulSet deletion;
- storefront access logs record only time, method, path without query string,
  status, size and duration. They never record client addresses, user agents,
  referrers or query strings, which can carry order status tokens. nginx error
  logging is limited to critical messages, because error lines include the client
  address and the full request line.

The default ingress namespace selector is portable. Some CNI/ingress setups
SNAT traffic; add only their observed source CIDRs through private values.

## Updating bundled application files

The chart packages the public ShopBridge plugin and deterministic demo seed so
it can install without downloading mutable repository content. After changing
those sources, synchronize and verify the chart copies:

```sh
bash scripts/sync-helm-chart-files.sh
bash scripts/check-helm-chart.sh
```

CI rejects stale chart copies, leaked private deployment indicators, unpinned
images, rendered Secret objects, and invalid Helm templates.
