# Talos USD verifier live drill

- Recorded at: 2026-08-23T15:12Z
- Operator: Codex deployment session authorized by Max (GiraeffleAeffle)
- Target: `https://woo-usd.agentcart.eu`
- Scope: Tempo Moderato testnet only; no real money and no production chain

## Deployment

The `agentcart-demo/woo-usd-verifier` Deployment is live with one Ready
replica, zero restarts, a Bound 1 GiB PVC, and a restricted NetworkPolicy. It
runs as non-root from the immutable image:

`ghcr.io/giraeffleaeffle/agentcart-shopbridge-verifier@sha256:689e62705ec34112b053fbfc0461e26477055678cb3eb00ccfa1437c79de75e8`

The `woo-usd` storefront is also Ready with zero restarts. Its public manifest
reports `production_ready=true`, `external_verifier_only` checkout,
`require_mutations` signed requests, Tempo testnet settlement verification, and
live testnet refunds. The verifier health response reported no missing or
invalid configuration, SQLite immediate-transaction locking, durable and
writable replay state, and a required writable replay journal.

## Quote-bound payment and refund

The endpoint harness created quote
`woo_quote_2652effd-9b94-4953-a42e-2c2b1a85a4e4` for 1,578 cents USD,
including 500 cents shipping and one VAT line. Quote hash
`a12ac8ced588bced255956a1a75efae7f8d3f36ac88ea45c3699613abc7f9fd8`
was bound to payment-contract hash
`aab9c536f26bf7eb677cd595a384cc698a3fa50c6d77b3f75af0fb9fe1b9dc80`.

Tempo transaction
`0x10556e9076df171228c35ea0f0a5378e6a4f0b7dc3446df147ec1e8af04e598c`
settled 15.78 pathUSD from
`0x2cbd9b394fa407bd299b4ab74d796795659187a9` to
`0x39a0134d5140e499ce1d8bceffdbbd7523108531` in block `32135079`.
WooCommerce order `54` entered `processing` only after the verifier returned
`state=verified` and `real_settlement_verified=true`.

Cancellation did not claim that funds moved back. The separate refund for
1,578 cents used transaction
`0xb56ad3fcb63768d20e29ae5486b83122a7c7bdbc95c1678d91da09534bd7d009`
in block `32135086`. It transferred 15.78 pathUSD back to the original payer,
was bound to the original payment reference and quote hash, and returned
`state=rail_refund_verified`, `refund_status=succeeded`, and
`real_refund_verified=true`.

Independent public-RPC receipt inspection found successful receipts and the
expected TIP-20 `Transfer` logs in both directions for 15,780,000 base units
(six decimals).

## Negative and replay boundaries

The same live endpoint harness recorded these fail-closed responses:

- unknown/expired quote: HTTP 409, `agentcart_quote_expired`;
- mismatched quote hash: HTTP 409, `agentcart_quote_mismatch`;
- refund without an idempotency key: HTTP 400,
  `agentcart_refund_idempotency_key_required`.

A separate non-economic verifier probe reused the already-settled transaction
reference with conflicting quote metadata. The verifier rechecked the public
onchain transfer and returned HTTP 409 with `replay_conflict=true` and
`replay_bucket=payments`. The stored payment claim was not replaced: replay
counts remained exactly one payment, one refund request, and one refund.

## Persistence and recovery

Before and after a Kubernetes rollout restart, SQLite contained the exact same
three bucket counts: `payments=1`, `refund_requests=1`, and `refunds=1`. The
replacement verifier pod became Ready with zero restarts, and post-probe health
still reported a durable, writable, required SQLite store and writable required
journal. The journal contained four entries after the expected conflict probe.

A SQLite online backup was retained on the verifier PVC as
`/data/replay-store-20260823T142043Z.sqlite`. Its SHA-256 is
`f7f5d083284781f99a32c75748fa3844893d05285326ec56ac71f48855101d2d`.
The private deployment receipt and secret-bearing inputs remain outside Git.

## Remaining operations gate

The replay conflict emitted a warning event, but alert delivery was explicitly
skipped with `reason=no_verifier_alert_webhook_configured`. This proves alert
generation, not alert delivery. `verifier_alert_delivery_result.md` therefore
remains intentionally incomplete until a real receiver is configured and a
delivery is observed.
