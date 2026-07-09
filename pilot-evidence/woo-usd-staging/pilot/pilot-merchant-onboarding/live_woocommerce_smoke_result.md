# live_woocommerce_smoke_result

- Scope: `pilot_gate`
- Owner id: `pilot-merchant-onboarding`
- Recorded at: 2026-07-05T21:06Z
- Operator: Max (GiraeffleAeffle), recorded via Claude Code session
- Command or source: `AGENTCART_WOO_SMOKE_REQUIRE_PRODUCTION_READY=1 AGENTCART_WOO_SMOKE_REQUIRE_REAL_REFUND_VERIFIER_EVIDENCE=1 scripts/woocommerce-usd-mppx-settlement-smoke.sh`

## Evidence

- Environment: `https://woo-usd.agentcart.eu` (Hetzner staging, merchant id
  `agentcart-usd-staging-shop`), plugin release v1.11.1.
- Result: exit code 0 with both strict assertions enabled
  (`production_ready` contract and real refund verifier evidence required).
- This run supersedes the plain live smoke: it wraps
  `scripts/woocommerce-shopbridge-smoke.py --require-shipping` plus the
  mutable endpoint harness and a real `mppx` Tempo testnet settlement.
- Payment rail: `tempo-mpp` on **testnet** (pathUSD). This is intentionally
  not real settlement; see `pilot/pilot-payment-mode/payment_mode_decision_record.md`.

Key hash-linked results:

| Step | Result |
| --- | --- |
| Quote | `woo_quote_a70426e7-bcd0-47b2-87ef-7f4f39ead1e8`, 1578 cents USD (500 shipping, 1 VAT line) |
| Quote hash | `ab6f67fac8d048fde507b1882b215efb56ddfbd0403423e974586b04ba866467` |
| Approval hash | `65d4955e59c643dd177de3146692345f287e09f9e1b118890288749c590aec38` |
| Payment contract hash | `7648187b2c80678baae8259214bc84ea32f00d79711159c8789c2706f06b9274` |
| Settlement tx | `0x110e0bad0a2d2af65f96497192d9a9f430e7d3837c516f96ee76659a8fe2b4cf`, `real_settlement_verified=true` |
| Order | Woo order 95, `processing`, `payment_status=paid` |
| Expired-quote probe | 409 `agentcart_quote_expired` with recovery payload |
| Quote-hash-mismatch probe | 409 `agentcart_quote_mismatch` |
| Refund idempotency probe | 400 `agentcart_refund_idempotency_key_required` |
| Cancellation | `cancelled_refund_required`; aftercare explicitly refuses `money_returned` claim |
| Refund | Woo refund 96, on-chain ref `0x2fe4bfe1be0bc3fc7ed95aeb8af86c38a45a464d180ce447f3256cf83f9e8206`, `real_refund_verified=true`, state `rail_refund_verified`, 1578 cents fully refunded |
| Production setup | `production_complete=true` (6 checked steps) |

Full transcript (order status token redacted):
`pilot-evidence/woo-usd-staging/attachments/usd-mppx-settlement-smoke-2026-07-05.txt`
(sha256 `ec63aa4ea0620d43c3f061e484deaa6a5a8be0799aa29b34c8a14d5e93551b93`).

Note: this evidence covers the maintainer-run **staging merchant**. The
external (non-maintainer) merchant's shop needs its own live smoke run when it
joins the pilot.

## 2026-07-09 hardening rollout rerun

After the pinned-internal-verifier and SQLite replay-store rollout, the strict
MPP harness passed again. Woo order 101 used payment transaction
`0x786ac168d49ba11a0a2923efff790b06a0ea38aa34a63e360ec5c50cb6f7019e`;
Woo refund 102 used verifier-backed refund reference
`0x500b8e02ac26cdd586cad4637f1feda4a42f58a28895ed7207d078f48a28f153`.
The live capability reported the deployment-managed verifier pin active and
production readiness complete. See
`attachments/usd-hardening-rollout-2026-07-09.md` for the redacted deployment,
migration, backup-drill, payment, refund, and metrics record.
