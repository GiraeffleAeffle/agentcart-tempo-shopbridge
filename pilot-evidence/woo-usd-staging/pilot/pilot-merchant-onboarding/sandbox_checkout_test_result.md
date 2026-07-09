# sandbox_checkout_test_result

- Scope: `pilot_gate`
- Owner id: `pilot-merchant-onboarding`
- Recorded at: 2026-07-09T20:29Z
- Operator: Codex deployment session authorized by Max (GiraeffleAeffle)
- Command or source: `AGENTCART_WOO_SMOKE_REQUIRE_REAL_REFUND_VERIFIER_EVIDENCE=1 scripts/woocommerce-usd-mppx-settlement-smoke.sh`

## Evidence

The strict testnet checkout harness exited successfully. WooCommerce order 101
was created with `payment_status=paid` only after the external verifier accepted
the quote-bound Tempo MPP proof. Cancellation changed the lifecycle to
`cancelled_refund_required` and explicitly kept `money_returned=false`. A
separate verifier-backed refund then created Woo refund 102 for the full 1,578
cents with `real_refund_verified=true`. Expired quote, quote-hash mismatch,
replay, and missing-refund-idempotency probes produced their expected rejection
responses. All funds in this result are pathUSD on Tempo testnet.
