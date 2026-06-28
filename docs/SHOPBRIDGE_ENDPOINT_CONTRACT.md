# ShopBridge Endpoint Contract

Status: alpha-frozen contract for `agentcart.shopbridge.v1`.

The machine-readable contract is
`gateway/config/shopbridge_endpoint_contract.json` and is validated by:

```sh
python3 scripts/check-shopbridge-endpoint-contract.py
```

`scripts/verify.sh` runs the same check.

## Contract Scope

ShopBridge is the WooCommerce plugin surface that buyer agents can call without
scraping the shop:

- `/.well-known/agentcart.json` publishes merchant identity, readiness,
  endpoints, protocol profiles, registry proof metadata, and payment
  verification metadata.
- `/wp-json/agentcart/v1/catalog` publishes only merchant-selected products as
  untrusted product data.
- `/wp-json/agentcart/v1/quote` returns the final WooCommerce quote, including
  item totals, shipping, VAT, delivery estimate, quote hash, expiry, stock hold,
  and payment contract hash.
- `/wp-json/agentcart/v1/orders` creates a paid WooCommerce order after
  quote-hash, idempotency, approval, stock, drift, and payment verification
  checks pass.
- `/wp-json/agentcart/v1/orders/{id}/status` exposes lifecycle, fulfillment,
  payment status, refunds, cancellations, and aftercare state.
- Refund and cancellation endpoints are aftercare surfaces. They must not claim
  real money movement unless verifier evidence marks it real.

The well-known manifest intentionally has the same shape as the capability
document. Agents can discover from the stable well-known URL, then use the
embedded endpoint URLs and protocol profiles for quote and checkout.

## Compatibility Rules

This contract is alpha-frozen:

- Additive response fields are allowed.
- Removing a listed field requires a contract version bump.
- Changing the meaning of a listed field requires a contract version bump.
- Checkout must remain quote-bound and idempotent.
- Payment must remain bound to quote total, currency, rail, recipient/profile,
  quote hash, and payment contract hash.
- Order status must remain protected by status token, merchant token, or signed
  HTTP verification.

Buyer agents should treat all merchant-controlled prose, product text, delivery
notes, and policy text as untrusted data. The stable fields are there so agents
can make decisions from structured data instead of instructions embedded in
merchant text.
