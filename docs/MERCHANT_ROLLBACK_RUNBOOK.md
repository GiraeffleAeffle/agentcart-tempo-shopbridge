# Merchant Rollback And Revocation Runbook

Status: production-candidate alpha runbook for removing or rolling back a pilot
merchant without losing commerce audit evidence.

Use this when a ShopBridge merchant must be removed from buyer discovery, public
checkout must stop, or an AgentCart gateway/plugin release must be rolled back.

## Roles

- Incident commander: declares rollback scope, records timestamps, and decides
  when the merchant can re-enter discovery.
- Merchant operator: controls WordPress/WooCommerce, product exposure, plugin
  activation, and merchant-hosted revocation state.
- Registry operator: controls the hosted AgentCart registry alpha endpoint and
  verifies feed proof/transparency output.
- Gateway operator: controls the AgentCart service deployment and release
  rollback.
- Audit owner: exports and stores order, approval, payment, refund, registry,
  and release evidence before destructive cleanup.

## Required Inputs

Set these values before running commands:

```sh
export SHOP_URL="https://shop.example"
export WP_PATH="/var/www/html"
export MERCHANT_ID="shop.example"
export MERCHANT_DOMAIN="shop.example"
export REGISTRY_RECORD_HASH="replace-with-current-record-hash"
export REGISTRY_URL="https://agentcart.example"
export AGENTCART_REGISTRY_SUBMIT_TOKEN="replace-with-registry-submit-token"
export ROLLBACK_ID="rollback-$(date -u +%Y%m%dT%H%M%SZ)"
export PILOT_PRODUCT_ID="replace-with-product-id"
export ORDER_ID="replace-with-order-id"
export AGENTCART_PURCHASE_ID="replace-with-agentcart-purchase-id"
export AGENTCART_TOKEN="replace-with-agentcart-token"
export PREVIOUS_AGENTCART_COMMIT_OR_TAG="replace-with-previous-commit-or-tag"
```

Record the active release before changing anything:

```sh
git rev-parse HEAD
cat dist/agentcart-release.json
wp --path="$WP_PATH" plugin status agentcart-shopbridge
wp --path="$WP_PATH" option get agentcart_shopbridge_registry_connection_status --format=json
```

## Rollback Sequence

### 1. Freeze Buyer-Facing Checkout

Responsible operator: merchant operator.

Use WordPress admin first when available:

1. Open `WooCommerce -> AgentCart`.
2. Set checkout mode to `external_verifier_only` if verifier settlement remains
   healthy, or deactivate the plugin if public ShopBridge traffic must stop
   immediately.
3. Save Support Diagnostics before and after the change.

Equivalent WP-CLI commands:

```sh
wp --path="$WP_PATH" option update agentcart_shopbridge_checkout_mode external_verifier_only
wp --path="$WP_PATH" option update agentcart_shopbridge_signed_request_mode enforce
wp --path="$WP_PATH" transient delete --all
```

If the plugin itself is failing, deactivate it:

```sh
wp --path="$WP_PATH" plugin deactivate agentcart-shopbridge
wp --path="$WP_PATH" plugin status agentcart-shopbridge
```

Do not delete WooCommerce orders or refunds during this step.

### 2. Disable Pilot Product Exposure

Responsible operator: merchant operator.

Prefer switching to manual exposure and disabling the affected pilot products:

```sh
wp --path="$WP_PATH" option update agentcart_shopbridge_product_exposure_mode manual
wp --path="$WP_PATH" post meta update "$PILOT_PRODUCT_ID" _agentcart_enabled no
wp --path="$WP_PATH" cache flush
```

For a tag- or category-based pilot, remove the pilot tag/category from the
affected products or add a blocked category:

```sh
wp --path="$WP_PATH" post term remove "$PILOT_PRODUCT_ID" product_tag agentcart-safe
wp --path="$WP_PATH" option update agentcart_shopbridge_product_blocked_categories "agentcart-disabled"
```

Verify the public catalog no longer includes the product:

```sh
curl -fsS "$SHOP_URL/wp-json/agentcart/v1/catalog" | jq .
curl -fsS "$SHOP_URL/.well-known/agentcart.json" | jq .
```

### 3. Revoke Registry Discovery

Responsible operators: merchant operator and registry operator.

From WordPress admin, the merchant operator can click `Send revocation request`
under `WooCommerce -> AgentCart` after configuring the registry connection URL
and token. That action records the current record hash in the merchant-hosted
revocation document and sends a `revoke` request to the registry connection.

Registry operator fallback command:

```sh
cat > /tmp/agentcart-registry-revoke.json <<JSON
{
  "schema": "agentcart.shopbridge.registry_connection_request.v1",
  "operation": "revoke",
  "record_hash": "$REGISTRY_RECORD_HASH",
  "merchant_id": "$MERCHANT_ID",
  "domain": "$MERCHANT_DOMAIN",
  "reason": "pilot_rollback",
  "idempotency_key": "$ROLLBACK_ID-$REGISTRY_RECORD_HASH"
}
JSON

curl -fsS -X POST "$REGISTRY_URL/v1/registry/records" \
  -H "Authorization: Bearer $AGENTCART_REGISTRY_SUBMIT_TOKEN" \
  -H "Content-Type: application/json" \
  --data @/tmp/agentcart-registry-revoke.json | jq .
```

Verify the hosted alpha registry removed the active record, retained the
revocation, and appended a hash-chained transparency event:

```sh
curl -fsS "$REGISTRY_URL/v1/registry/records" | jq .
curl -fsS "$REGISTRY_URL/v1/registry/feed-proof" | jq .
curl -fsS "$REGISTRY_URL/v1/registry/transparency" | jq .
curl -fsS "$REGISTRY_URL/v1/registry/health" | jq .
```

Expected state:

- `entry_count` no longer includes the revoked merchant record.
- `revocation_count` includes `REGISTRY_RECORD_HASH`.
- `/v1/registry/feed-proof` lists the hash under `revocation_record_hashes`.
- `/v1/registry/transparency` has a `revoke` event with a valid chain.

The HTTP revocation path is covered by
`gateway/tests/test_agentcart.py::AgentCartTests.test_hosted_registry_revocation_http_updates_feed_proof_and_transparency`.

### 4. Roll Back The Gateway Release

Responsible operator: gateway operator.

If the gateway release is the suspected source, roll back to the previous tested
commit or release tag:

```sh
git fetch --tags origin
git checkout "$PREVIOUS_AGENTCART_COMMIT_OR_TAG"
./scripts/verify.sh

docker compose \
  --env-file deploy/home-server/.env \
  -f deploy/home-server/docker-compose.yml \
  up -d --build agentcart

docker compose \
  --env-file deploy/home-server/.env \
  -f deploy/home-server/docker-compose.yml \
  logs --tail=100 agentcart
```

Verify the service-facing registry and monitor endpoints:

```sh
curl -fsS "$REGISTRY_URL/v1/registry/feed-proof" | jq .
curl -fsS "$REGISTRY_URL/v1/registry/health" | jq .
```

If the deployment uses a GitHub Release artifact rather than a local checkout,
pin rollback to the previous `agentcart-release.json` and verify checksums with:

```sh
python3 scripts/verify-release.py \
  --manifest dist/agentcart-release.json \
  --expected-source-commit "$PREVIOUS_AGENTCART_COMMIT"
```

### 5. Roll Back Or Deactivate The Plugin

Responsible operator: merchant operator.

If only the plugin release is bad, install the previous ZIP:

```sh
wp --path="$WP_PATH" plugin deactivate agentcart-shopbridge
wp --path="$WP_PATH" plugin install /secure/releases/agentcart-shopbridge-previous.zip --force
wp --path="$WP_PATH" plugin activate agentcart-shopbridge
wp --path="$WP_PATH" plugin status agentcart-shopbridge
```

If the shop must leave the pilot, deactivate the plugin and keep the plugin data
until audit export is complete:

```sh
wp --path="$WP_PATH" plugin deactivate agentcart-shopbridge
```

Uninstall is allowed only after the audit owner confirms exports are preserved.
The plugin uninstall policy removes ShopBridge settings and ephemeral locks, but
preserves WooCommerce orders, refunds, cancellation history, payment
verification metadata, approval metadata, and product-level AgentCart metadata.
That contract is checked by
`woocommerce-shopbridge/tests/test_plugin_contracts.py::ShopBridgePluginContractTests.test_uninstall_cleanup_preserves_commerce_audit_metadata`.

### 6. Preserve Audit Evidence

Responsible operator: audit owner.

Export evidence before uninstalling, deleting products, or rotating away access
tokens:

```sh
wp --path="$WP_PATH" post list --post_type=shop_order --post_status=any --format=json > "$ROLLBACK_ID-orders.json"
wp --path="$WP_PATH" post meta list "$ORDER_ID" --format=json > "$ROLLBACK_ID-order-$ORDER_ID-meta.json"
wp --path="$WP_PATH" option get agentcart_shopbridge_registry_connection_status --format=json > "$ROLLBACK_ID-registry-status.json"
wp --path="$WP_PATH" option get agentcart_shopbridge_registry_public_check --format=json > "$ROLLBACK_ID-registry-public-check.json"

curl -fsS "$REGISTRY_URL/v1/registry/records" > "$ROLLBACK_ID-registry-records.json"
curl -fsS "$REGISTRY_URL/v1/registry/feed-proof" > "$ROLLBACK_ID-registry-feed-proof.json"
curl -fsS "$REGISTRY_URL/v1/registry/transparency" > "$ROLLBACK_ID-registry-transparency.json"
```

For service-backed buyer paths, export AgentCart audit packets:

```sh
curl -fsS "$REGISTRY_URL/v1/audit/$AGENTCART_PURCHASE_ID/export" \
  -H "Authorization: Bearer $AGENTCART_TOKEN" \
  > "$ROLLBACK_ID-audit-export-$AGENTCART_PURCHASE_ID.json"
```

Store the evidence folder with the incident record and link it from the pilot
evidence gate.

## Recovery Criteria

The incident commander can end rollback only when all are true:

- the affected merchant no longer appears in active registry discovery;
- public catalog and quote responses no longer expose disabled pilot products;
- the gateway is running a verified commit or release artifact;
- the merchant plugin is deactivated, reverted, or reconfigured;
- order/audit exports are stored outside the WordPress host;
- the registry feed proof and transparency log are attached to the incident;
- no buyer-facing aftercare message claims refund execution without verifier
  evidence.

## Re-Entry

A merchant can re-enter the pilot by publishing a fresh registry record with a
new `updated_at`, confirming the public manifest/proof/revocation endpoints,
running the WooCommerce live smoke, and adding a new registry submit event. Do
not reuse a revoked record hash.
