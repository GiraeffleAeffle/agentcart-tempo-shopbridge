# AgentCart ShopBridge for WooCommerce

AgentCart ShopBridge exposes an opt-in WooCommerce store to household or agentic commerce clients through a machine-readable merchant interface:

- public discovery: `/.well-known/agentcart.json`
- public registry domain proof: `/.well-known/agentcart-registry-proof.json`
- public catalog: `/wp-json/agentcart/v1/catalog`
- public product details: `/wp-json/agentcart/v1/products/{id}`
- public quote: `/wp-json/agentcart/v1/quote`
- paid order creation: `/wp-json/agentcart/v1/orders`
- order status and tracking: `/wp-json/agentcart/v1/orders/{id}/status`
- merchant-approved refund recording: `/wp-json/agentcart/v1/orders/{id}/refunds`

The merchant remains merchant of record. WooCommerce remains the source of truth for products, stock, tax setup, shipping, fulfillment, refunds, and customer support.

AgentCart-created orders intentionally clear WooCommerce's customer IP and user-agent fields before saving the order. Merchants still receive the shipping/billing data needed for fulfillment, but the bridge should not preserve network identifiers unless a production deployment explicitly adds a lawful reason and disclosure.

The public manifest uses `AGENTCART_SUPPORT_EMAIL` / `agentcart_shopbridge_support_email` only. It does not fall back to the WordPress admin email.

## Merchant Setup

### Install From ZIP

1. Download or build `dist/agentcart-shopbridge.zip`.
2. In WordPress admin, open `Plugins -> Add New -> Upload Plugin`.
3. Select the ZIP, install, and activate `AgentCart ShopBridge for WooCommerce`.
4. Open `WooCommerce -> AgentCart` and configure support, Tempo, verifier, and gateway settings.
5. Add or edit normal WooCommerce products.
6. Enable `Expose through AgentCart` on selected products, or bulk-enable the current published simple-product catalog from the ShopBridge settings page.

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
define('AGENTCART_PAYMENT_VERIFIER_URL', 'https://verifier.example.com/agentcart/tempo');
define('AGENTCART_PAYMENT_VERIFIER_TOKEN', 'replace-with-verifier-token');
define('AGENTCART_SUPPORT_EMAIL', 'support@example.com');
```

Constants override values saved from the WordPress admin settings page.

### WordPress Plugin Directory

The ZIP works with WordPress admin's `Upload Plugin` flow today. It will not appear in the searchable `Plugins -> Add New` directory until it is submitted to and approved by the WordPress.org plugin directory. That production publication path requires WordPress.org plugin guidelines compliance, a `readme.txt`, licensing review, assets/screenshots, an SVN-based plugin repository, and ongoing update/security maintenance.

For private merchant onboarding before WordPress.org approval, distribute the ZIP from a GitHub release or direct download page. Native update notifications require either WordPress.org hosting, a custom update server, or an updater mechanism; GitHub alone is not enough for standard WordPress plugin search/update discovery.

For the hackathon demo, `AGENTCART_SHOPBRIDGE_TOKEN` lets a trusted AgentCart gateway create orders after its own approval and payment proof flow.

For production, configure `AGENTCART_PAYMENT_VERIFIER_URL`. Public agents can then create orders only when the verifier confirms the quote-bound receipt.

The settings page also shows:

- discovery manifest URL
- registry domain proof URL and configured state
- catalog, quote, and paid-order endpoints
- whether the Tempo recipient is configured
- whether Stripe/card MPP has a Stripe profile and verifier configured
- whether the plugin is in demo token mode or external verifier mode
- a merchant onboarding checklist

## Product Exposure

Products are not exposed just because they are published in WooCommerce. The
merchant must explicitly enable AgentCart exposure. This can be done per product
with `Expose through AgentCart`, or in one onboarding step by bulk-enabling the
current published simple-product catalog from `WooCommerce -> AgentCart`. The
plugin maps enabled Woo fields into an agent-readable product schema:

- stable `product_id` and Woo `source_product_id`
- SKU, title, description, category, brand, unit size
- image URLs
- VAT-inclusive price hint
- stock/availability
- shipping regions from WooCommerce's configured shipping countries
- `eligible_for_agent_checkout`

Future hardening can add category rules, quantity limits, and richer
merchant-side policies, but the default product seam remains explicit opt-in.

## Quote Binding

The quote endpoint computes final terms and stores them server-side for 15 minutes:

- line items
- VAT lines
- shipping
- delivery estimate/window
- merchant-of-record details
- delivery country requirements
- `quote_hash`
- payment requirements

The order endpoint reloads the stored quote and rejects mismatched or expired quotes. Stock is rechecked before order creation. The quote explicitly says stock is not reserved unless the merchant later adds real stock-hold support. Quote creation rejects unsupported destination countries before payment.

## Payment Verification

There are two modes:

- `trusted_agentcart_token`: hackathon/demo mode. The merchant token authenticates the gateway, and the plugin checks receipt amount/currency against the stored quote. This is not sufficient for production settlement.
- `external_verifier`: production shape. The plugin POSTs quote, quote hash, expected amount/currency/merchant, and receipt to `AGENTCART_PAYMENT_VERIFIER_URL`. Only verifier responses with `ok: true` create a paid WooCommerce order.

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

## Discovery

The minimum discovery mechanism is the well-known manifest:

```text
https://shop.example/.well-known/agentcart.json
```

Agents and directories can crawl this, validate the manifest, and index the catalog endpoint.

For registry-based discovery, the plugin also serves a merchant-owned domain
proof:

```text
https://shop.example/.well-known/agentcart-registry-proof.json
```

The proof document is used with `signature_alg: https-domain-proof`. It binds
the shop domain to the final canonical registry record hash. The plugin
auto-generates the stable registry claim, claim hash, record hash, and
`updated_at` timestamp from merchant identity, payment, shipping, and endpoint
settings.

1. Open `WooCommerce -> AgentCart` and copy the manifest URL.
2. Ask the AgentCart registry operator to build the final registry record from
   that manifest URL, or use a future hosted AgentCart registry connection.
   Operators can use:
   `python3 gateway/scripts/registry_record.py build --manifest-url https://shop.example/.well-known/agentcart.json`.
3. The proof endpoint publishes the fields AgentCart verifies before including
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
- carrier, tracking number, and tracking URL when present

The plugin reads common Woo tracking metadata such as `_wc_shipment_tracking_items`, `_tracking_provider`, `_tracking_number`, and `_tracking_url`. Real DHL/UPS/DHL Paket status requires the merchant to use a shipment/tracking plugin or carrier API integration that writes tracking data back to WooCommerce.

## Standard Compatibility

ShopBridge is intentionally a merchant adapter, not a replacement for ACP/AP2/UCP/MPP. The practical layering is:

- WooCommerce plugin exposes catalog, quote, order, fulfillment.
- MPP/x402-style payment proof pays or proves payment.
- ACP/AP2/UCP-style clients can be supported by writing translators that map their cart/checkout concepts to the same quote and order endpoints.
