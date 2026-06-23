=== AgentCart ShopBridge for WooCommerce ===
Contributors: agentcart
Tags: woocommerce, agents, checkout, machine payments, mpp
Requires at least: 6.4
Tested up to: 6.6
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

Agents can discover opt-in products, request final WooCommerce-backed quotes,
bind approval/payment to the quote hash, create paid WooCommerce orders after
payment verification, read status/tracking metadata, and draft safe aftercare
actions.

== Features ==

* Merchant-controlled product exposure: manual checkbox, WooCommerce tag,
  WooCommerce categories, or all published simple products.
* Blocked categories, product-level checkout exclusion, max quantity limits,
  and product-specific shipping country overrides.
* WooCommerce cart, tax, shipping, stock, and order creation integration.
* Quote hash binding and single-use quote consumption.
* Baseline REST rate limits and idempotency/replay checks.
* External payment verifier hook for quote-bound Tempo MPP, Stripe/card MPP, or
  other rails.
* Merchant-token-protected refund and cancellation endpoints.
* Normalized fulfillment tracking adapter metadata from common WooCommerce
  shipment/tracking plugin fields.
* Structured policy metadata for restricted goods, perishables, deposits,
  final-sale goods, substitutions, refunds, and cancellations, inferred from
  WooCommerce tags, categories, and attributes with optional explicit product
  overrides.
* Auto-managed domain-proof, revocation, and registry-onboarding bundle fields
  for an AgentCart merchant registry.

== Installation ==

1. Upload `agentcart-shopbridge.zip` from WordPress admin under `Plugins -> Add New -> Upload Plugin`.
2. Activate `AgentCart ShopBridge for WooCommerce`.
3. Open `WooCommerce -> AgentCart`.
4. Configure stable merchant id, support email, payment recipient or Stripe
   profile, verifier URL, checkout mode, and product exposure mode.
5. Add normal WooCommerce products and expose only the products that are safe
   for agent checkout.
6. Share the registry bundle URL with a registry or local buyer-agent test.
7. Test the manifest, catalog, quote, and a non-production checkout path before
   public use.

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
