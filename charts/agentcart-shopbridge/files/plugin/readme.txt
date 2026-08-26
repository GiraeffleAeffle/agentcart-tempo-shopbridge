=== AgentCart ShopBridge ===
Contributors: agentcart
Tags: woocommerce, agents, checkout, machine-payments, mpp
Requires at least: 6.4
Tested up to: 7.1
Requires PHP: 8.1
Requires Plugins: woocommerce
Stable tag: 0.2.0
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
* `/.well-known/agentcart-registry-records/{sha256}.json`
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
* Non-mutating product exposure preview and saved catalog snapshot diff showing
  included, blocked, added, removed, changed, and out-of-policy products before
  registry refresh or catalog publication.
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
* Production readiness rejects shared secrets shorter than 32 characters and
  rejects reuse across merchant, verifier, and signed-request credential roles.
* Registry transparency actions to refresh the merchant-owned claim metadata
  and check public manifest/proof/revocation/bundle endpoints before registry
  ingestion.
* Optional hosted registry connection that submits the generated registry bundle
  or a merchant revocation request to a merchant-configured registry endpoint.
  Hosted submission and revocation requests do not write to the onchain
  registry.
* Four public onchain identity settings (controller, CAIP-2 chain, registry
  contract, and deterministic record id) plus exact finalized-readiness status.
  ShopBridge does not request, store, or use a controller private key.
* Content-addressed merchant-hosted Registry Record snapshots. Existing hashes
  are never rewritten when merchant settings produce a new record.
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
ingest or cache a merchant-owned discovery record or revocation intent, and let
the merchant view registry-side health, manifest freshness, and monitor state
without copy/paste. An accepted hosted request is not an onchain transaction or
proof of finalized contract inclusion.

For the supervised Tempo Moderato pilot, clicking "Check registry health" also
sends read-only JSON-RPC requests to `https://rpc.moderato.tempo.xyz`. The
plugin reads chain id, finalized/deployment block headers, registry bytecode,
and the configured public merchant record, domain mapping, deterministic record
id, and record-hash revocation state. It sends only the public registry contract
address, controller, record id/hash, normalized shop hostname for Ethereum
Keccak hashing, and standard RPC method parameters. It does not send a private
key, signature, buyer address, order, product, or payment data. State reads are
pinned to one canonical finalized block hash. This check can satisfy WordPress
onchain readiness through that pinned RPC; hosted registry health/event data is
displayed only as operator-reported compatibility evidence.

No verifier or registry connection is contacted for public catalog or quote
browsing. A verifier is called only after the merchant configures a Payment
verifier URL in `WooCommerce -> AgentCart` or defines
`AGENTCART_PAYMENT_VERIFIER_URL`. A registry connection is called only after the
merchant configures a Registry connection URL or defines
`AGENTCART_REGISTRY_CONNECTION_URL` and presses one of the registry connection
or registry health action buttons. The pinned Tempo RPC is called only when an
administrator presses the registry health button.

Payment verifier URLs must resolve to public IP addresses unless
`AGENTCART_ALLOW_PRIVATE_PAYMENT_VERIFIER_URL=1` is set for a local or staging
environment. Do not enable that private-network override for production.

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
a bearer token for private monitor status. That hosted response cannot confer
canonical-chain readiness. The exact destination, terms, and privacy policy
depend on the registry service configured by the merchant. The pinned RPC is
subject to the [Tempo Terms of Use](https://wallet.tempo.xyz/support/terms-of-service)
and [Tempo Privacy Policy](https://wallet.tempo.xyz/support/privacy-policy).

== Installation ==

1. Upload `agentcart-shopbridge.zip` from WordPress admin under `Plugins -> Add New -> Upload Plugin`.
2. Activate `AgentCart ShopBridge`.
3. Open `WooCommerce -> AgentCart`.
4. Use the Quick Start panel to prepare sandbox access defaults when secrets are
   not managed through `wp-config.php`. This generates local signed-request
   compatibility and registry metadata, but does not expose products or configure
   payment recipients. The same panel can run a sandbox quote check and a
   guided admin dry checkout through the WooCommerce-backed quote/order path,
   then clean up the test quote, stock hold, and test order. The dry checkout
   does not call the live payment verifier, move funds, or prove settlement.
5. Configure stable merchant id, support email, payment recipient or Stripe
   profile, optional x402 exact-payment settings, Payment verifier URL,
   checkout mode, optional signed-request mode, and product exposure mode.
   Use Credential Actions on the same page to generate or rotate local tokens
   when they are not managed through wp-config.php.
6. Add normal WooCommerce products and expose only the products that are safe
   for agent checkout.
7. Preview product exposure, review the catalog diff, and save a current
   catalog snapshot after confirming the agent-readable catalog looks right.
8. In the Registry Proof section, refresh metadata when stable identity/payment
   settings change, then run the public endpoint check.
9. For the supervised Tempo Moderato pilot, give the public registry bundle URL
   and a merchant-controlled public controller address to the pilot observer.
   The observer prepares the four public onchain identity values. Save those
   values in WordPress, refresh metadata, and approve the reviewed zero-value
   registry transaction in the external controller wallet. Never put a private
   key, seed phrase, wallet session, or signature in WordPress.
10. Ask the observer to verify the exact wallet transaction and active record
    at a finalized block, then use Check registry health. The plugin performs
    its own pinned read-only Tempo RPC state check. A hosted bundle submission
    is optional and does not replace finalized verification.
11. Test the manifest, catalog, quote, and guided non-production checkout path
    before public use. Run a separate buyer test with the configured external
    verifier before claiming testnet settlement.
12. Use Support Diagnostics on `WooCommerce -> AgentCart` when setup, registry,
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

= Does Submit registry bundle register the shop onchain? =

No. It sends the public bundle to the configured hosted registry for cache,
compatibility, and monitoring. The supervised onchain pilot separately prepares
a transaction for the merchant's external controller wallet and requires exact
verification at a finalized block. ShopBridge stores only the four public
onchain identity values, never the wallet secret. The documented enrollment is
Tempo Moderato testnet only; Ethereum mainnet, Gnosis mainnet, and Tempo
production are not approved.

= Does the guided checkout test prove payment settlement? =

No. It is an admin-only dry run that exercises the WooCommerce-backed quote and
order path, creates and cancels a test order, and does not call the live payment
verifier or move funds. Test the configured external verifier separately before
making a settlement claim.

= Are refunds and cancellations public? =

No. Refund and cancellation endpoints require the merchant token. Buyer-facing
skills should create request drafts unless they run behind a trusted AgentCart
gateway with merchant authorization.

= What is removed on uninstall? =

The uninstall routine removes ShopBridge settings, locks, stock-hold state, and
temporary quote/rate-limit transients. It also removes the plugin-owned public
onchain identity settings and content-addressed Registry Record archive; copy
committed records to a separately operated append-only archive before uninstall
in any production design. It intentionally preserves WooCommerce orders,
refunds, cancellation history, payment verification metadata, and product-level
AgentCart metadata so merchants retain their commerce audit trail.

== Changelog ==

= 0.2.0 =

* Separate privacy-preserving comparison quotes from approval-ready final
  quotes, require a complete country-specific delivery address before payment
  verification, and report gross serialized VAT as included in quote totals.

= 0.1.0 =

* Alpha ShopBridge plugin for WooCommerce-backed agent catalog, quote, order,
  status, refund, and cancellation flows.
