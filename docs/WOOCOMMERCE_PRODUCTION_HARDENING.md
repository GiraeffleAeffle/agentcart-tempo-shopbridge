# WooCommerce Plugin Production Hardening

> Status: production-candidate alpha with explicit WooCommerce plugin gaps.
> This document separates implemented hardening from the remaining controls
> needed before live merchant pilots.

The ShopBridge plugin now includes merchant-controlled
product exposure modes: manual per-product opt-in, WooCommerce product tag, or
WooCommerce product categories, or all published simple products. It also
supports a non-mutating product exposure preview with saved catalog snapshot
diffs, blocked category slugs,
per-product AgentCart max quantities, a product-level checkout exclusion
override, per-product shipping-country overrides, soft AgentCart quote holds
for managed stock, a fail-closed hard reservation adapter contract, structured
restricted-goods metadata, and structured commerce-policy metadata for
perishable, deposit-bearing, final-sale, and substitution-sensitive products in
catalog, quote, order status, and refund policy payloads. Restricted-goods
matches are blocked from catalog, quote, and checkout by default unless the
merchant explicitly allows the product after confirming their compliance and
human-review flow. Store-level
aftercare policy defaults for returns, substitutions, and cancellation requests
are configurable from the AgentCart settings page and bound into the quote hash.
Production merchant onboarding still needs the controls below. The catalog diff
lets merchants review added, removed, and changed agent-readable products before
refreshing registry metadata or treating a preview as the current baseline.

## Merchant Admin Readiness

The settings page should block or warn until:

- support email is configured and public;
- merchant id is stable;
- HTTPS public domain is used;
- shipping countries are configured;
- tax/VAT setup is active;
- terms and refund policy URLs are present;
- Tempo recipient or Stripe profile is configured;
- external payment verifier URL/token are configured;
- demo trusted-token mode is disabled for public agents.

## Product Controls

Current behavior exposes only published simple products selected by the
merchant's exposure mode, excludes product-level checkout blocks, and rejects
quote or checkout quantities above each product's AgentCart limit. Blocked
category slugs are excluded across every exposure mode, and restricted-goods
matches are blocked by default while still telling buyer agents when human
review is required. Product-specific
shipping countries and quote-bound stock holds are rechecked before paid order
creation. Hard stock-hold mode requires merchant inventory hooks to reserve,
confirm, and release provider-backed reservations, and fails closed when those
hooks are missing. Perishable, deposit-bearing, final-sale, and
substitution-sensitive labels are surfaced as item policy metadata and
preserved onto order status/refund policy responses for buyer-agent aftercare.
Store-level returns, substitution, and cancellation-request defaults are also
preserved onto paid AgentCart orders. A merchant-token-protected cancellation
endpoint can cancel eligible AgentCart-created Woo orders before fulfillment
tracking or terminal order states, records an idempotent cancellation event, and
does not execute refunds. The admin exposure preview shows which products are
included, blocked by product/category policy, or outside the selected exposure
mode before merchants rely on the catalog.
Production should add richer product controls:

- product-specific return/refund/substitution policy overrides beyond inferred
  labels and store defaults;
- cancellation state-machine support that coordinates with shipment providers,
  picker/packer workflows, and rail refund execution;
- provider-specific hard reservation adapters for shops that need actual
  inventory holds before payment. The current plugin includes the adapter
  contract, binds hold metadata into the quote hash, confirms hard reservations
  before paid order creation, and returns recovery hints when the quote can no
  longer be used.

## Security

- Use external verifier mode for public order creation.
- Keep token mode for trusted local gateways only.
- Keep the plugin's baseline REST rate limits enabled for catalog, quote,
  order, status, refund, cancellation, and `.well-known` registry/discovery
  endpoints. Current `429` errors include retry and reset metadata.
- Run the live abuse smoke with `AGENTCART_WOO_SMOKE_ABUSE_RATE_LIMITS=1`
  against staging or pilot shops to exhaust quote, checkout, status, refund,
  cancellation, and `.well-known` registry buckets and verify `429` metadata.
- Run the live production setup smoke with
  `AGENTCART_WOO_SMOKE_REQUIRE_PRODUCTION_READY=1` before admitting a shop to a
  pilot. This fails while production-required setup steps such as merchant
  identity, verifier mode, or registry proof are still incomplete.
- Add host-level reverse-proxy/CDN/WAF rate limits for public production shops.
- Store and reject used transaction references.
- Require idempotency keys for order creation and refunds.
- Bind order creation to stored quote hash, payment contract hash, expiry, and
  single-use quote lock.
- Reject refund amounts above the remaining refundable amount.
- Reject reused refund references before creating WooCommerce refund records.
- Keep privacy defaults: do not store requester IP/user-agent unless merchant
  config and disclosures require it.

## Tests To Add

The repo currently has source-level plugin contract tests plus PHP syntax
checks. A production plugin still needs a WordPress/WooCommerce integration test
harness for end-to-end endpoint behavior.

- order endpoint rejects expired quotes;
- order endpoint rejects amount/currency/quote hash mismatch;
- replayed payment transaction reference is rejected;
- refund endpoint requires an idempotency key;
- refund endpoint rejects amount above paid total;
- refund endpoint returns existing refund for exact idempotent replay;
- refund endpoint rejects conflicting idempotent replay;
- reused external refund reference is rejected;
- refund verifier failure does not create Woo refund;
- cancellation endpoint requires an idempotency key;
- cancellation endpoint rejects shipped or terminal orders;
- cancellation endpoint never claims real refund execution;
- unsupported destination country fails before payment;
- products outside the selected exposure mode are absent from catalog and
  rejected in quote;
- product-level checkout exclusions are absent from catalog and rejected in
  quote;
- over-limit quantities are rejected instead of silently clamped in both quote
  and order creation;
- no customer IP/user-agent is saved for agent-created orders by default.

## Packaging

For a real WordPress plugin release:

- keep plugin versioning and changelog current in the plugin header and
  WordPress `readme.txt`;
- keep uninstall cleanup policy conservative: remove settings and ephemeral
  state, preserve commerce audit metadata;
- run `scripts/check-wordpress-official-gates.py --strict` after installing the
  `woocommerce-shopbridge/composer.json` dev tools; strict mode also runs the
  official Plugin Check plugin in the bundled local WordPress/Woo stack;
- add GitHub release zip build;
- document required WooCommerce versions;
- document verifier contract and merchant compliance caveats.
