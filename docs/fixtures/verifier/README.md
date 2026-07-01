# Verifier Fixtures

These fixtures pin the production-shaped external verifier boundary between
ShopBridge and a rail-specific verifier. Payment fixtures include the
`payment_contract_hash` that binds quote total, currency, quote hash, selected
rail, and destination/profile into one verifier contract.
Success fixtures also include `replay_reference` and `replay_request_hash`, so
the verifier can distinguish exact idempotent retries from replay conflicts.

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
- `euro-stablecoin-rail-plan.json`: current rail decision fixture recording why
  the first Tempo staging shop should be USD and why EURC/EURe belong behind an
  x402/EVM verifier path.
- `negative/*.json`: mutation cases that must be rejected before a paid order
  or rail refund is accepted.

Validate them with:

```sh
python3 scripts/verify-verifier-fixtures.py
```

The validator also checks that the WooCommerce plugin still builds verifier
payloads with the required contract fields and that the Stripe sandbox verifier
keeps replay-protection hooks for payment, refund request, and refund
references, including request-hash conflict checks.
