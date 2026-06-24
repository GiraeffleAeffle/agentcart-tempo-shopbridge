# AgentCart ShopBridge for WooCommerce

AgentCart ShopBridge exposes an opt-in WooCommerce store to household or agentic commerce clients through a machine-readable merchant interface:

- public discovery: `/.well-known/agentcart.json`
- public registry domain proof: `/.well-known/agentcart-registry-proof.json`
- public registry onboarding bundle: `/.well-known/agentcart-registry-bundle.json`
- public catalog: `/wp-json/agentcart/v1/catalog`
- public product details: `/wp-json/agentcart/v1/products/{id}`
- public quote: `/wp-json/agentcart/v1/quote`
- paid order creation: `/wp-json/agentcart/v1/orders`
- order status and tracking: `/wp-json/agentcart/v1/orders/{id}/status`
- merchant-approved refund recording: `/wp-json/agentcart/v1/orders/{id}/refunds`
- merchant-approved cancellation recording: `/wp-json/agentcart/v1/orders/{id}/cancellations`

The merchant remains merchant of record. WooCommerce remains the source of truth for products, stock, tax setup, shipping, fulfillment, refunds, and customer support.

AgentCart-created orders intentionally clear WooCommerce's customer IP and user-agent fields before saving the order. Merchants still receive the shipping/billing data needed for fulfillment, but the bridge should not preserve network identifiers unless a production deployment explicitly adds a lawful reason and disclosure.

The public manifest uses `AGENTCART_SUPPORT_EMAIL` / `agentcart_shopbridge_support_email` only. It does not fall back to the WordPress admin email.
It also publishes configured-only `protocol_profiles[]` so buyer agents can
select the ShopBridge commerce adapter, MPP payment adapter, Stripe/card MPP
adapter, x402 exact-payment adapter, registry mapping, or signed-request auth
profile before requesting a quote.

## Merchant Setup

### Install From ZIP

1. Download or build `dist/agentcart-shopbridge.zip`.
2. In WordPress admin, open `Plugins -> Add New -> Upload Plugin`.
3. Select the ZIP, install, and activate `AgentCart ShopBridge`.
4. Open `WooCommerce -> AgentCart` and configure merchant id, support, Tempo or Stripe/card profile, verifier, and gateway settings.
5. Add or edit normal WooCommerce products.
6. Choose a product exposure mode: manual product checkbox, WooCommerce product tag, or all published simple products.

To rebuild the ZIP from source:

```sh
./scripts/package-woocommerce-plugin.sh
```

### Manual Install

Copy `woocommerce-shopbridge/agentcart-shopbridge` into:

```text
wp-content/plugins/agentcart-shopbridge
```

Then activate the plugin in WordPress and open `WooCommerce -> AgentCart`.

### Deployment Configuration

Configure merchant/payment constants in `wp-config.php` or equivalent deployment config when you want deployment-managed values:

```php
define('AGENTCART_MERCHANT_ID', 'my-shop');
define('AGENTCART_SHOPBRIDGE_TOKEN', 'replace-with-random-shared-secret');
define('AGENTCART_TEMPO_NETWORK', 'testnet');
define('AGENTCART_TEMPO_RECIPIENT_ADDRESS', '0x...');
define('AGENTCART_STRIPE_PROFILE_ID', 'profile_test_...');
define('AGENTCART_X402_NETWORK', 'eip155:84532');
define('AGENTCART_X402_ASSET', '0x...');
define('AGENTCART_X402_ASSET_SYMBOL', 'USDC');
define('AGENTCART_X402_ASSET_DECIMALS', 6);
define('AGENTCART_X402_ASSET_CURRENCY', 'USD');
define('AGENTCART_X402_PAY_TO', '0x...');
define('AGENTCART_X402_FACILITATOR_URL', 'https://facilitator.example.com');
define('AGENTCART_X402_MAX_TIMEOUT_SECONDS', 300);
define('AGENTCART_PAYMENT_VERIFIER_URL', 'https://verifier.example.com/agentcart/tempo');
define('AGENTCART_PAYMENT_VERIFIER_TOKEN', 'replace-with-verifier-token');
define('AGENTCART_CHECKOUT_MODE', 'external_verifier_only'); // trusted_token_or_verifier or external_verifier_only
define('AGENTCART_SIGNED_REQUEST_MODE', 'require_checkout'); // off, allow, require_checkout, require_mutations, or require_all_sensitive
define('AGENTCART_SIGNED_REQUEST_SECRET', 'replace-with-request-signing-secret');
define('AGENTCART_SUPPORT_EMAIL', 'support@example.com');
define('AGENTCART_RETURNS_URL', 'https://shop.example/returns');
define('AGENTCART_SUBSTITUTION_POLICY', 'approval_required'); // approval_required, not_allowed, or merchant_allowed
define('AGENTCART_CANCELLATION_WINDOW_MINUTES', 30);
define('AGENTCART_PRODUCT_EXPOSURE_MODE', 'tag'); // manual, tag, category, or all
define('AGENTCART_PRODUCT_EXPOSURE_TAG', 'agentcart-safe');
```

Constants override values saved from the WordPress admin settings page.
Merchants who do not manage settings through deployment config can set the same
stable merchant id from `WooCommerce -> AgentCart`. The id is published in the
manifest, registry bundle, quote approvals, payment verification payloads, and
WooCommerce order audit metadata.

### WordPress Plugin Directory

The ZIP works with WordPress admin's `Upload Plugin` flow today. It will not appear in the searchable `Plugins -> Add New` directory until it is submitted to and approved by the WordPress.org plugin directory. That production publication path requires WordPress.org plugin guidelines compliance, a `readme.txt`, licensing review, assets/screenshots, an SVN-based plugin repository, and ongoing update/security maintenance.

See `docs/WORDPRESS_ORG_SUBMISSION.md` for the current submission checklist.
Run the local package guard before submitting:

```sh
./scripts/check-wordpress-plugin-package.py --zip dist/agentcart-shopbridge.zip
```

For private merchant onboarding before WordPress.org approval, distribute the ZIP from a GitHub release or direct download page. Native update notifications require either WordPress.org hosting, a custom update server, or an updater mechanism; GitHub alone is not enough for standard WordPress plugin search/update discovery.

The plugin package includes a WordPress-style `readme.txt` and an
`uninstall.php` cleanup routine. Uninstall removes ShopBridge settings,
ephemeral locks, stock-hold state, quote transients, and rate-limit transients.
It intentionally preserves WooCommerce orders, refunds, cancellation events,
payment verification metadata, and product-level AgentCart metadata so merchants
retain their commerce audit trail.

The `WooCommerce -> AgentCart` admin page includes a guided setup checklist for
merchant id/support, agent-safe product exposure, WooCommerce tax and
shipping setup, payment verifier configuration, registry proof publication, and
sandbox quote/order testing. The same public-safe setup state is also exposed in
the capability document for remote onboarding tools.

For a live endpoint smoke test against a seeded or staging shop:

```sh
python3 scripts/woocommerce-shopbridge-smoke.py \
  --base-url http://127.0.0.1:8098 \
  --require-shipping \
  --require-vat-lines
```

Set `AGENTCART_WOO_SMOKE_BASE_URL` to make `./scripts/verify.sh` include this
live check. The smoke test validates manifest/capability setup state, registry
bundle/proof/revocation hash binding, catalog exposure, and WooCommerce-backed
quote totals without creating an order.

For the hackathon demo, `AGENTCART_SHOPBRIDGE_TOKEN` lets a trusted AgentCart gateway create orders after its own approval and payment proof flow.

For production, configure `AGENTCART_PAYMENT_VERIFIER_URL` and set checkout mode
to `external_verifier_only`. Public agents can then create orders only when the
verifier confirms the quote-bound receipt; the merchant token no longer falls
back to demo settlement for order creation.

The settings page also shows:

- discovery manifest URL
- stable merchant id
- registry domain proof URL and configured state
- registry onboarding bundle URL for registry or local buyer-agent ingestion
- catalog, quote, and paid-order endpoints
- aftercare policy defaults for returns, substitutions, and cancellation
  requests
- whether the Tempo recipient is configured
- whether Stripe/card MPP has a Stripe profile and verifier configured
- whether checkout allows trusted token fallback or requires an external verifier
- a merchant onboarding checklist

## Product Exposure

Products are not exposed just because they are published in WooCommerce. The
merchant chooses one exposure mode in `WooCommerce -> AgentCart`:

- `manual`: expose only products with the `Expose through AgentCart` checkbox.
- `tag`: expose published simple products that have a normal WooCommerce product
  tag, default `agentcart-safe`.
- `category`: expose published simple products in configured WooCommerce
  product category slugs.
- `all`: expose all published simple products. This is intended for shops whose
  entire simple-product catalog is safe for agent checkout.

Merchants can also configure blocked category slugs. Blocked categories are
excluded from catalog, quote, and checkout in every exposure mode.

The legacy bulk action is still available for merchants who want to mark the
current catalog for manual mode in one onboarding step. The plugin maps exposed
Woo fields into an agent-readable product schema:

- stable `product_id` and Woo `source_product_id`
- SKU, title, description, category, category slugs, brand, unit size
- structured `package_size` from normal WooCommerce product weight settings,
  so buyer agents can compare grocery-style unit value without extra merchant
  setup
- structured `tags`, `labels`, `dietary_tags`, and `allergens` from normal
  WooCommerce product tags and attributes, so buyer agents can apply household
  constraints without merchant-specific setup
- structured `restricted_goods` policy metadata for age-restricted, medical,
  weapon/fireworks, and stored-value categories when normal Woo labels indicate
  those risks
- structured `commerce_policy` metadata for perishable, deposit-bearing,
  final-sale, and substitution-sensitive products when normal Woo tags,
  attributes, or categories indicate those handling rules
- image URLs
- VAT-inclusive price hint
- stock/availability
- shipping regions from WooCommerce's configured shipping countries or the
  product-specific AgentCart shipping country override
- `eligible_for_agent_checkout`
- `max_quantity`
- `agentcart_policy`

Each product can also define an `AgentCart max quantity`. Quote requests above
that limit are rejected before cart or payment work begins, and checkout
revalidates the limit before creating the paid WooCommerce order. Products
marked `Exclude from AgentCart checkout` or assigned to a blocked category are
absent from catalog results and rejected in quotes and checkout, even in tag,
category, or all-product exposure modes. Use those controls for age-gated,
regulated, local-pickup-only, deposit, or manual-review products.

Product-specific AgentCart shipping countries are optional; empty values inherit
the store's WooCommerce shipping countries. Quote and checkout both reject
products whose override no longer permits the destination country.

Deposit, perishable, final-sale, and substitution-sensitive labels are surfaced
as policy metadata, not hidden checkout logic. Buyer agents can ask for approval
or show aftercare warnings, while the merchant still uses normal WooCommerce
products, tags, attributes, categories, refund settings, and support workflows.
Future hardening can add richer merchant-side policy overrides and return
automation, but the default product seam remains merchant-controlled and
fail-closed.

## Quote Binding

The quote endpoint computes final terms and stores them server-side for the
configured quote/stock-hold window, default 15 minutes:

- line items
- VAT lines
- shipping
- delivery estimate/window
- merchant-of-record details
- delivery country requirements
- `quote_hash`
- payment requirements

The order endpoint reloads the stored quote under a quote-level checkout lock
and rejects mismatched, expired, already-consumed, or concurrently-consumed
quotes. Exact idempotent replays return the existing order; different checkout
attempts cannot reuse the same merchant quote. Stock is rechecked before order
creation. When soft quote holds are enabled, managed-stock products are held in
an AgentCart-scoped hold index until quote expiry or paid-order creation. This
does not reduce WooCommerce stock, but it prevents concurrent AgentCart quotes
from ignoring each other. Quote creation rejects unsupported shop or
product-specific destination countries before payment.

## Endpoint Rate Limits

ShopBridge applies a lightweight fixed-window rate limit in its REST permission
callbacks before catalog, product, quote, order, status, or refund handlers run.
The public capability document exposes the current buckets and limits under
`rate_limits`.

Limits are scoped to a hashed client key derived from the request IP, user
agent, and merchant token hint when present. The plugin does not store raw IPs
or user-agent strings in order records. Exceeded requests return `429` with
`retry_after_seconds` metadata.

These plugin limits are a production baseline, not a replacement for a reverse
proxy, CDN/WAF, or host-level rate limiting on public shops.

## Payment Verification

There are two payment verification modes:

- `trusted_agentcart_token`: hackathon/demo mode. The merchant token authenticates the gateway, and the plugin checks receipt amount/currency against the stored quote. This is not sufficient for production settlement.
- `external_verifier`: production shape. The plugin POSTs quote, quote hash, expected amount/currency/merchant, and receipt to `AGENTCART_PAYMENT_VERIFIER_URL`. Only verifier responses with `ok: true` create a paid WooCommerce order.

There are also two checkout authorization modes:

- `trusted_token_or_verifier`: local/private mode. A trusted gateway token can
  create quote-bound demo orders when no verifier is configured.
- `external_verifier_only`: production mode. Order creation requires an external
  verifier; the merchant token cannot create a paid order through demo fallback.

Signed request mode is an additional request-authentication gate. When
configured with `AGENTCART_SIGNED_REQUEST_SECRET`, ShopBridge can require
HMAC-SHA256 signatures for checkout only, checkout/refund/cancellation, or all
sensitive quote/checkout/status/refund/cancellation endpoints. The signature
binds:

```text
agentcart-signed-request-v1
METHOD
/request/path?query
sha-256=<hex body digest>
nonce
expires_at_unix_seconds
signer
```

The required headers are `X-AgentCart-Signed-Method`,
`X-AgentCart-Signed-Path`, `X-AgentCart-Content-Digest`,
`X-AgentCart-Nonce`, `X-AgentCart-Expires-At`, `X-AgentCart-Signer`, and
`X-AgentCart-Signature`. Nonces are single-use until expiry.

The verifier response must bind the payment to the exact quote and transaction.
See `../docs/VERIFIER_CONTRACT.md` for the production verifier contract. Minimal
success response:

```json
{
  "ok": true,
  "quote_hash": "sha256...",
  "amount_cents": 1840,
  "currency": "EUR",
  "rail": "tempo-mpp",
  "network": "testnet",
  "recipient": "0x...",
  "transaction_reference": "0x...",
  "real_settlement_verified": false
}
```

The plugin rejects mismatched quote hash, amount, currency, rail, Tempo network/recipient for Tempo payments, Stripe profile for Stripe/card payments, and reused transaction references.

If using direct Tempo MPP/stablecoin settlement, the merchant needs a Tempo-compatible recipient account/address or a provider that holds/settles on its behalf. Tempo's documented defaults are USD-stablecoin assets: USDC.e on mainnet and pathUSD on testnet. WooCommerce may still quote in EUR; in that case the external verifier/payment provider must bind FX conversion and settlement terms to the quote before creating a paid order. If using a PSP/custodial setup, the merchant can avoid managing raw keys directly, but still needs onboarding/KYC/payout configuration with that provider.

Stripe/card MPP is represented as a separate rail in `payment_requirements.protocols[]`.
It is only marked available when both `AGENTCART_STRIPE_PROFILE_ID` and
`AGENTCART_PAYMENT_VERIFIER_URL` are configured. The verifier is responsible for
validating Stripe Shared Payment Token credentials and returning a quote-bound
payment reference before the plugin creates a paid WooCommerce order.

## Refunds

The refund endpoint is merchant-token protected:

```text
POST /wp-json/agentcart/v1/orders/{id}/refunds
```

Request:

```json
{
  "refund_idempotency_key": "refund-order-123-1",
  "amount_cents": 1480,
  "reason": "Customer requested refund",
  "rail": "stripe-card-mpp",
  "requested_reference": "refund-order-123-1"
}
```

`refund_idempotency_key`, `idempotency_key`, `requested_reference`, or the
`Idempotency-Key` header is required. Exact replays return the existing refund.
Conflicting replays are rejected. Refund amounts above the remaining refundable
amount are rejected instead of silently clamped.

In trusted-token demo mode, the endpoint creates a WooCommerce refund record and
returns `real_refund_verified: false`. No card, EUR, Tempo, stablecoin, or Stripe
funds are moved.

In production external-verifier mode, the plugin first POSTs an `operation:
refund` payload to `AGENTCART_PAYMENT_VERIFIER_URL`. The verifier must execute or
verify the rail refund and return:

```json
{
  "ok": true,
  "amount_cents": 1480,
  "currency": "EUR",
  "quote_hash": "sha256...",
  "original_transaction_reference": "0x...",
  "rail": "stripe-card-mpp",
  "refund_reference": "re_...",
  "real_refund_verified": true
}
```

Only after that does the plugin record the WooCommerce refund metadata. Reused
refund references on the same order are rejected. For Stripe/card, the verifier
should use Stripe refund APIs. For Tempo/stablecoin, the verifier should create
or verify the refund transfer back to the source wallet and return the refund
transaction reference.

## Cancellations

The cancellation endpoint is merchant-token protected:

```text
POST /wp-json/agentcart/v1/orders/{id}/cancellations
```

Request:

```json
{
  "cancellation_idempotency_key": "cancel-order-123-1",
  "reason": "Customer requested cancellation",
  "requested_reference": "cancel-order-123-1"
}
```

The endpoint only applies to AgentCart-created WooCommerce orders. It rejects
orders that are already cancelled, completed, refunded, failed, or have shipment
tracking attached. Successful cancellation changes the WooCommerce order status
to `cancelled`, stores an AgentCart cancellation event, and returns whether a
separate rail refund is still required.

Cancellation does not move money. Paid orders still need a separate refund
through `/refunds` and the configured external verifier before agents or
merchants should claim that real funds were returned.

Quotes include store-level aftercare policy defaults for returns, refunds,
substitutions, and cancellation requests. The quote hash binds those defaults,
and the paid order stores them so buyer-facing order status continues to reflect
the terms that were approved at checkout.

Order status and refund policy responses also include item-level commerce
policy summaries. Perishable, deposit-bearing, final-sale,
substitution-sensitive, and restricted items can require buyer-agent review
before refunds, returns, cancellations, or substitutions. This is guidance and
audit metadata for agents; real refund authority still stays with WooCommerce
plus the configured payment verifier.

## Discovery

The minimum discovery mechanism is the well-known manifest:

```text
https://shop.example/.well-known/agentcart.json
```

Agents and directories can crawl this, validate the manifest, and index the catalog endpoint.

For registry-based discovery, the plugin also serves a merchant-owned domain
proof and a registry onboarding bundle:

```text
https://shop.example/.well-known/agentcart-registry-proof.json
https://shop.example/.well-known/agentcart-registry-bundle.json
```

The proof document is used with `signature_alg: https-domain-proof`. It binds
the shop domain to the final canonical registry record hash. The plugin
auto-generates the stable registry claim, claim hash, record hash, and
`updated_at` timestamp from merchant identity, payment, shipping, and endpoint
settings.

The bundle contains `registry_record`, `record_hash`, the expected proof
document, an empty revocation document, and a one-entry `registry_feed`.
Registries can ingest that bundle directly, and local buyer-agent tests can use
it as `SHOPBRIDGE_REGISTRY_URL`.

1. Open `WooCommerce -> AgentCart`.
2. In `Registry Proof`, use `Refresh registry metadata` after stable identity,
   payment, shipping, endpoint, or policy settings change.
3. Use `Check public registry endpoints` to verify the manifest, proof,
   revocation document, and bundle before registry ingestion.
4. Copy the registry bundle URL.
5. Ask the AgentCart registry operator to ingest the bundle, or use a future
   hosted AgentCart registry connection.
   Operators can use:
   `python3 gateway/scripts/registry_record.py build --manifest-url https://shop.example/.well-known/agentcart.json`.
6. The proof endpoint publishes the fields AgentCart verifies before including
   the shop in quote tournaments.

An onchain registry can make sense as an identity and integrity anchor, not as the product catalog itself. A useful registry record would contain:

- merchant id
- domain
- manifest URL
- registry claim hash
- payment network
- payment recipient
- timestamp/version
- proof URL under `/.well-known/`

Catalogs, quotes, stock, delivery estimates, and consumer terms should stay offchain because they change often and may contain regulated commerce data.

## Delivery And Tracking

Order creation returns a `status_url` and one-time order status token. The status endpoint returns:

- Woo order status
- paid/unpaid state
- merchant-estimated delivery window
- carrier, tracking number, tracking URL, normalized tracking status, and the
  tracking metadata source when present

The plugin reads common Woo tracking metadata such as
`_wc_shipment_tracking_items`, AfterShip-style metadata, ParcelPanel-style
metadata, `_tracking_provider`, `_tracking_number`, `_tracking_url`, and
`_tracking_status`. It normalizes those into `fulfillment.tracking` with
`tracking_status`, `source`, `adapter`, timestamps, and confidence. Real DHL/UPS
/DHL Paket polling still requires the merchant to use a shipment/tracking plugin
or carrier API integration that writes tracking data back to WooCommerce.

## Standard Compatibility

ShopBridge is intentionally a merchant adapter, not a replacement for ACP/AP2/UCP/MPP. The practical layering is:

- WooCommerce plugin exposes catalog, quote, order, fulfillment.
- MPP/x402-style payment proof pays or proves payment.
- ACP/AP2/UCP-style clients can be supported by writing translators that map their cart/checkout concepts to the same quote and order endpoints.
