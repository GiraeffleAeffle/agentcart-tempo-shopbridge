# WooCommerce Plugin Production Hardening

> Status: roadmap/design notes. The hackathon repo implements the demo slice; this document lists production work that is not complete yet.


The ShopBridge plugin is demo-capable and now includes explicit per-product
AgentCart opt-in. Production merchant onboarding still needs the controls below.

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

Current demo behavior exposes only published simple products that the merchant
marks as AgentCart-enabled. Production should add richer product/category
controls:

- per-product max quantity;
- blocked categories;
- shipping-country restrictions;
- age/restricted goods flags;
- return/refund policy overrides;
- merchant-side stock reservation option.

## Security

- Use external verifier mode for public order creation.
- Keep token mode for trusted local gateways only.
- Rate-limit quote and order endpoints.
- Store and reject used transaction references.
- Add idempotency keys for order creation and refunds.
- Bind order creation to stored quote hash and expiry.
- Keep privacy defaults: do not store requester IP/user-agent unless merchant
  config and disclosures require it.

## Tests To Add

- order endpoint rejects expired quotes;
- order endpoint rejects amount/currency/quote hash mismatch;
- replayed transaction reference is rejected;
- refund endpoint rejects amount above paid total;
- refund verifier failure does not create Woo refund;
- unsupported destination country fails before payment;
- disabled product is absent from catalog and rejected in quote;
- no customer IP/user-agent is saved for agent-created orders by default.

## Packaging

For a real WordPress plugin release:

- add plugin versioning and changelog;
- add uninstall cleanup policy;
- add PHPCS/WordPress coding standard checks;
- add GitHub release zip build;
- document required WooCommerce versions;
- document verifier contract and merchant compliance caveats.
