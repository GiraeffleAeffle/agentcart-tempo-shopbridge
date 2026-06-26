=== AgentCart ShopBridge ===
Contributors: agentcart
Tags: woocommerce, agents, checkout, machine-payments, mpp
Requires at least: 6.4
Tested up to: 7.0
Requires PHP: 8.1
Requires Plugins: woocommerce
Stable tag: 0.1.0
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Expose an opt-in WooCommerce catalog, quote, paid-order, order-status, refund, and cancellation interface for buyer agents.

== Description ==

AgentCart ShopBridge lets a WooCommerce merchant expose machine-readable
commerce endpoints for buyer-side agents without replacing WooCommerce as the
merchant backend.

WooCommerce remains the source of truth for products, stock, tax, shipping,
fulfillment, refunds, and support. The plugin exposes:

* `/.well-known/agentcart.json`
* `/.well-known/agentcart-registry-proof.json`
* `/.well-known/agentcart-registry-revocations.json`
* `/.well-known/agentcart-registry-bundle.json`
* `/wp-json/agentcart/v1/catalog`
* `/wp-json/agentcart/v1/quote`
* `/wp-json/agentcart/v1/orders`
* `/wp-json/agentcart/v1/orders/{id}/status`
* `/wp-json/agentcart/v1/orders/{id}/refunds`
* `/wp-json/agentcart/v1/orders/{id}/cancellations`
* `/wp-json/agentcart/v1/support-diagnostics` for WooCommerce managers

Agents can discover opt-in products, request final WooCommerce-backed quotes,
bind approval/payment to the quote hash, create paid WooCommerce orders after
payment verification, read status/tracking metadata, and draft safe aftercare
actions.

== Features ==

* Merchant-controlled product exposure: manual checkbox, WooCommerce tag,
  WooCommerce categories, or all published simple products.
* Non-mutating product exposure preview showing included, blocked, and
  out-of-policy products before catalog publication.
* Blocked categories, product-level checkout exclusion, max quantity limits,
  and product-specific shipping country overrides.
* WooCommerce cart, tax, shipping, stock, and order creation integration.
* Soft quote stock holds plus optional fail-closed hard reservation adapter
  hooks for merchant inventory systems.
* Quote hash binding, payment contract hash binding, and single-use quote
  consumption.
* Baseline REST and `.well-known` endpoint rate limits with retry metadata,
  plus idempotency/replay checks.
* External payment verifier hook for quote-bound Tempo MPP, Stripe/card MPP, or
  other rails.
* Configured-only manifest protocol profiles so agents can choose ShopBridge,
  MPP, Stripe/card MPP, x402, or registry adapters before quote calls.
* Optional x402 exact-payment shim that emits quote-bound `PAYMENT-REQUIRED`
  metadata when network, asset, payTo, currency, decimals, and verifier are
  configured.
* Optional signed-request mode with HMAC-SHA256 or RSA-SHA256 signatures that
  bind method, path, body digest, nonce, expiry, and signer for quote,
  checkout, status, refund, and cancellation calls.
* Bounded signed-request audit trail that stores verification outcomes and
  sanitized hashes instead of raw request bodies, signatures, or nonces.
* Admin support diagnostics download with readiness, registry, signed-request,
  sandbox-check, verifier, catalog, and WooCommerce setup summaries redacted for
  merchant support.
* Merchant-token-protected refund and cancellation endpoints.
* Admin actions to generate or rotate local merchant and verifier tokens while
  respecting secrets managed in wp-config.php.
* Registry transparency actions to refresh the merchant-owned claim metadata
  and check public manifest/proof/revocation/bundle endpoints before registry
  ingestion.
* Optional hosted registry connection that submits the generated registry bundle
  or a merchant revocation request to a merchant-configured registry endpoint.
* Normalized fulfillment tracking adapter metadata from common WooCommerce
  shipment/tracking plugin fields.
* Structured policy metadata for restricted goods, perishables, deposits,
  final-sale goods, substitutions, refunds, and cancellations, inferred from
  WooCommerce tags, categories, and attributes with optional explicit product
  overrides. Restricted-goods matches are blocked from AgentCart catalog,
  quote, and checkout by default unless the merchant explicitly allows the
  product after confirming their review and compliance flow.
* Auto-managed domain-proof, revocation, and registry-onboarding bundle fields
  for an AgentCart merchant registry.

== External Services ==

ShopBridge can call a merchant-configured payment verifier URL when creating a
paid order or recording a verified refund. The verifier confirms that the buyer
agent's payment or refund receipt matches the WooCommerce quote amount,
currency, merchant id, quote hash, payment contract hash, and configured
payment destination.

ShopBridge can also call a merchant-configured registry connection URL when the
merchant clicks "Submit registry bundle", "Send revocation request", or "Check
registry health" in `WooCommerce -> AgentCart`. Those requests let a registry
ingest or revoke the merchant-owned discovery record, and let the merchant view
the registry-side health, manifest freshness, and monitor snapshot for the
current record without copy/paste.

No verifier or registry connection is contacted for public catalog or quote
browsing. A verifier is called only after the merchant configures a Payment
verifier URL in `WooCommerce -> AgentCart` or defines
`AGENTCART_PAYMENT_VERIFIER_URL`. A registry connection is called only after the
merchant configures a Registry connection URL or defines
`AGENTCART_REGISTRY_CONNECTION_URL` and presses one of the registry connection
or registry health action buttons.

The verifier request can include the stored quote, selected order/refund fields,
payment receipt fields supplied by the buyer agent, merchant id, payment rail,
payment destination, amount, currency, quote hash, payment contract hash,
optional x402 `PAYMENT-SIGNATURE` payload, and idempotency/reference values.
The exact destination, terms, and privacy policy depend on the verifier service
configured by the merchant.

The registry request can include the generated registry record, record hash,
manifest URL, registry bundle URL, domain proof document, revocation document,
public endpoint check result, merchant id, shop domain, and an idempotency key.
The registry health check can fetch registry health and monitor JSON derived
from that configured registry URL and can send the registry connection token as
a bearer token for private monitor status. The exact destination, terms, and
privacy policy depend on the registry service configured by the merchant.

== Installation ==

1. Upload `agentcart-shopbridge.zip` from WordPress admin under `Plugins -> Add New -> Upload Plugin`.
2. Activate `AgentCart ShopBridge`.
3. Open `WooCommerce -> AgentCart`.
4. Use the Quick Start panel to prepare sandbox access defaults when secrets are
   not managed through `wp-config.php`. This generates local signed-request
   compatibility and registry metadata, but does not expose products or configure
   payment recipients. The same panel can run a sandbox quote check and a
   guided checkout test through the WooCommerce-backed quote/order path, then
   clean up the test quote, stock hold, and test order.
5. Configure stable merchant id, support email, payment recipient or Stripe
   profile, optional x402 exact-payment settings, Payment verifier URL,
   checkout mode, optional signed-request mode, and product exposure mode.
   Use Credential Actions on the same page to generate or rotate local tokens
   when they are not managed through wp-config.php.
6. Add normal WooCommerce products and expose only the products that are safe
   for agent checkout.
7. In the Registry Proof section, refresh metadata when stable identity/payment
   settings change, then run the public endpoint check.
8. Share the registry bundle URL with a registry or local buyer-agent test, or
   configure the optional Registry connection URL and submit the bundle from the
   Registry Proof section.
9. Test the manifest, catalog, quote, and guided non-production checkout path
   before public use.
10. Use Support Diagnostics on `WooCommerce -> AgentCart` when setup, registry,
    signed request, verifier, or checkout support needs a redacted JSON bundle.

== Frequently Asked Questions ==

= Does this replace WooCommerce checkout? =

No. ShopBridge adds an agent-facing catalog, quote, order, status, refund, and
cancellation interface. Human browser checkout still uses the merchant's normal
WooCommerce checkout and payment gateways.

= Does the plugin move money? =

No. The plugin creates paid WooCommerce orders only after a trusted token flow
or external verifier confirms a quote-bound payment receipt. Production
checkout should use external-verifier-only mode, and settlement/refunds must be
performed or verified by the configured payment rail/verifier.

= Are refunds and cancellations public? =

No. Refund and cancellation endpoints require the merchant token. Buyer-facing
skills should create request drafts unless they run behind a trusted AgentCart
gateway with merchant authorization.

= What is removed on uninstall? =

The uninstall routine removes ShopBridge settings, locks, stock-hold state, and
temporary quote/rate-limit transients. It intentionally preserves WooCommerce
orders, refunds, cancellation history, payment verification metadata, and
product-level AgentCart metadata so merchants retain their commerce audit trail.

== Changelog ==

= 0.1.0 =

* Alpha ShopBridge plugin for WooCommerce-backed agent catalog, quote, order,
  status, refund, and cancellation flows.
