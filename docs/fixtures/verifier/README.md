# Verifier Fixtures

These fixtures pin the production-shaped external verifier boundary between
ShopBridge and a rail-specific verifier. Payment fixtures include the
`payment_contract_hash` that binds quote total, currency, quote hash, selected
rail, and destination/profile into one verifier contract.
Stripe and Tempo success fixtures also include `replay_reference` and
`replay_request_hash`. x402 uses a durable authorization reservation bound to
the quote and payment contract, and returns the same stored settlement on retry.

- `payment-request.stripe-card-mpp.json`: payload ShopBridge sends before
  creating a paid WooCommerce order.
- `payment-success.stripe-card-mpp.json`: verifier response ShopBridge accepts
  for a Stripe/card MPP payment.
- `refund-request.stripe-card-mpp.json`: payload ShopBridge sends before
  recording a rail-verified refund.
- `refund-success.stripe-card-mpp.json`: verifier response ShopBridge accepts
  for a Stripe/card MPP refund.
- `payment-request.tempo-mpp.json`: USD/pathUSD payload ShopBridge sends before
  creating a paid WooCommerce order through a Tempo verifier.
- `payment-success.tempo-mpp.json`: verifier response ShopBridge accepts for a
  real Tempo settlement claim.
- `refund-request.tempo-mpp.json`: USD/pathUSD refund payload that binds the
  refund recipient to the original payer address.
- `refund-success.tempo-mpp.json`: verifier response ShopBridge accepts for a
  real Tempo refund transfer claim.
- `payment-request.x402-compatible.json`: x402 v2 exact Base Sepolia USDC
  authorization, with padded-base64 `x402_payment_signature`.
- `payment-success.x402-compatible.json`: confirmed Transfer and AuthorizationUsed
  settlement response, including the encoded `PAYMENT-RESPONSE` header value.
  No x402 refund fixtures exist: refunds return `x402_refund_unsupported`.
- `euro-stablecoin-rail-plan.json`: current rail decision fixture recording why
  the first Tempo staging shop should be USD and why EURC/EURe belong behind an
  x402/EVM verifier path.
- `negative/*.json`: mutation cases that must be rejected before a paid order
  or rail refund is accepted.

Validate them with:

```sh
python3 scripts/verify-verifier-fixtures.py
```

The validator checks fixture data, not implementation text. Runtime regressions
in `gateway/tests/verifier-x402.test.mjs` exercise the real verifier HTTP boundary,
local facilitator and RPC fakes, durable replay recovery and refund rejection.
The other verifier behavioral tests and replay smokes cover existing MPP rails.
