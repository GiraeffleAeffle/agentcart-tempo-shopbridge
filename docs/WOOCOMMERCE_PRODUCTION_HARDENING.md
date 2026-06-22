# WooCommerce Plugin Production Hardening

> Status: roadmap/design notes. The hackathon repo implements the demo slice; this document lists production work that is not complete yet.


The ShopBridge plugin is demo-capable and now includes merchant-controlled
product exposure modes: manual per-product opt-in, WooCommerce product tag, or
WooCommerce product categories, or all published simple products. It also
supports blocked category slugs, per-product AgentCart max quantities, a
product-level checkout exclusion override, and structured restricted-goods
metadata in catalog and quote payloads. Production merchant onboarding still
needs the controls below.

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
metadata tells buyer agents when human review is required. Production should add
richer product controls:

- shipping-country restrictions;
- perishable/deposit handling;
- return/refund policy overrides;
- merchant-side stock reservation option.

## Security

- Use external verifier mode for public order creation.
- Keep token mode for trusted local gateways only.
- Keep the plugin's baseline REST rate limits enabled for catalog, quote,
  order, status, and refund endpoints.
- Add host-level reverse-proxy/CDN/WAF rate limits for public production shops.
- Store and reject used transaction references.
- Require idempotency keys for order creation and refunds.
- Bind order creation to stored quote hash, expiry, and single-use quote lock.
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
- public REST endpoints return `429` after rate-limit exhaustion;
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

- add plugin versioning and changelog;
- add uninstall cleanup policy;
- add PHPCS/WordPress coding standard checks;
- add GitHub release zip build;
- document required WooCommerce versions;
- document verifier contract and merchant compliance caveats.
