# refund_policy_statement

- Scope: `pilot_gate`
- Owner id: `pilot-payment-mode`
- Recorded at: 2026-07-09T20:29Z
- Operator: Max (GiraeffleAeffle), confirmed through the authorized testnet rollout and refund verification
- Command or source: live ShopBridge policy contract and strict post-deployment Tempo MPP refund smoke

## Evidence

Refund policy for the supervised external beta:

1. **Cancellation never executes a refund.** A cancellation moves the order to
   `cancelled_refund_required`; buyer-facing aftercare explicitly refuses the
   `money_returned` claim until a verified refund exists. (Verified in the
   2026-07-05 rehearsal.)
2. **A refund is only called real with rail verifier evidence.** ShopBridge
   sets `real_refund_verified=true` only after the external verifier returns a
   rail refund receipt bound to the original transaction reference and quote
   hash. Anything else is recorded as a request, not as money moved.
3. **Refund requests are idempotent and replay-protected.** An idempotency key
   is required (400 otherwise); refund references are single-use in the
   verifier replay store.
4. **Pilot scope: testnet only.** Refunds during the pilot are executed by the
   staging refund wallet on Tempo testnet in pathUSD. No real funds are owed
   to or by any pilot participant; consumer-rights refund obligations do not
   attach to test orders.
5. **Merchant stays in control.** The merchant reviews refund requests in
   WooCommerce as merchant of record; the advertised merchant policy
   (`requires_merchant_review=true`, `rail_refund_requires_verifier=true`)
   is served from ShopBridge settings and treated as untrusted display text
   by buyer agents.
6. **Production note.** Before any real-money pilot, this statement must be
   replaced with a rail-specific policy (Stripe/card MPP or EUR stablecoin)
   including settlement timelines and dispute handling. That rail does not
   exist yet; see `docs/SETTLEMENT_OPTIONS.md`.

### Operational confirmation

The 2026-07-09 testnet run demonstrated the policy: cancellation left the paid
order in `cancelled_refund_required` with `money_returned=false`; only the
separate Tempo verifier response allowed refund 102 to report
`real_refund_verified=true`. This statement governs the supervised testnet
pilot only and is not a consumer-facing real-money refund policy.
