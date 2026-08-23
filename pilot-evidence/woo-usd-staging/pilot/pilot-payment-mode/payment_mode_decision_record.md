# payment_mode_decision_record

- Scope: `pilot_gate`
- Owner id: `pilot-payment-mode`
- Recorded at: 2026-07-09T20:29Z
- Operator: Max (GiraeffleAeffle), confirmed through the authorized hardening and rollout session
- Command or source: payment-mode decision in the Codex task plus strict Tempo MPP deployment smoke on 2026-07-09

## Evidence

### Decision

The supervised external beta uses the **trusted testnet flow**: Tempo
`tempo-mpp` rail with **pathUSD on testnet**, checkout mode
`external_verifier_only`, on-chain settlement verification enabled
(`tempo_settlement_mode=verify`), live **testnet** refunds
(`tempo_refund_mode=live`), and signed checkout requests
(`signed_request_mode=require_checkout`).

**No real money moves in either direction during this pilot.** All settlement
and refund evidence is on Tempo testnet and is labeled as such in order,
status, and aftercare payloads. Participating merchants are told this
explicitly before setup (see `docs/PILOT_MERCHANT_BRIEF.md`).

### Why this mode

- It is one of the three modes the beta checklist allows, and the only one
  that also exercises the full production-shaped path: quote-bound payment
  requirements, external verifier, replay protection, and rail-verified
  refunds.
- The 2026-07-05 rehearsal on `https://woo-usd.agentcart.eu` passed with
  `AGENTCART_WOO_SMOKE_REQUIRE_PRODUCTION_READY=1` and
  `AGENTCART_WOO_SMOKE_REQUIRE_REAL_REFUND_VERIFIER_EVIDENCE=1`
  (see `pilot/pilot-merchant-onboarding/live_woocommerce_smoke_result.md`).
- Real-settlement rails for a normal merchant (Stripe/card MPP, EUR
  stablecoin) are not implemented yet, and the checklist blocks unaudited
  real settlement anyway.

### Checklist exit criteria mapping

- Public checkout uses an external verifier: yes — `external_verifier_only`;
  trusted-token-only public checkout stays disabled.
- Demo/testnet payments labeled as not real settlement: yes — rail metadata
  carries `network=testnet`; this record and the merchant brief repeat it.
- Real refund claims require verifier evidence: yes —
  `real_refund_verified=true` only after an on-chain refund receipt
  (rehearsal refund ref
  `0x2fe4bfe1be0bc3fc7ed95aeb8af86c38a45a464d180ce447f3256cf83f9e8206`).
- Idempotency and replay checks enabled: yes — rehearsal probes returned
  409/400 rejections for expired quote, quote-hash mismatch, and missing
  refund idempotency key.

### Blocked for this pilot

- Any real-money settlement or refund on any rail.
- Refund or "money returned" claims without verifier evidence.
- Public checkout gated only by a merchant token.
- Connecting real payment credentials (Stripe keys, mainnet wallets) to any
  pilot shop.

### Operator confirmation

Max confirmed that the current production-shaped scope is a staging shop on a
blockchain testnet using a dollar-denominated stablecoin and authorized the
Hetzner rollout on 2026-07-09. The strict post-rollout MPP payment and refund
test exited successfully. Moving to real shops or real money is a separate
decision and is not authorized by this record.

## Talos confirmation (2026-08-23)

The same decision was exercised after the workload moved from the former VM to
the Talos cluster. The public manifest still reported `external_verifier_only`,
required signed mutations, Tempo `testnet`, pathUSD settlement verification,
and live testnet refunds. A 15.78 pathUSD payment and refund succeeded in both
directions, and no Ethereum or Tempo production network was touched. See
`attachments/talos-usd-verifier-live-drill-2026-08-23.md`.
