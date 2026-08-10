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

## Security behavior

- no service-account token is mounted;
- containers run without privilege escalation and drop all capabilities;
- WordPress runs with a read-only root filesystem;
- the application container never receives the MariaDB root password;
- public WordPress administration, login, XML-RPC, and user enumeration are
  denied at HAProxy Ingress;
- ShopBridge's four exact `/.well-known/` JSON documents remain public;
- default-deny NetworkPolicies isolate storefront and database pods;
- egress to private, loopback, link-local, and carrier-grade NAT ranges is
  denied for public HTTPS calls;
- persistent claims survive Helm uninstall and StatefulSet deletion.

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
