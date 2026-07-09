# diagnostic_collection_steps

- Scope: `pilot_gate`
- Owner id: `pilot-support-channel`
- Recorded at: 2026-07-05
- Operator: Max (GiraeffleAeffle), operational collection procedure recorded for the supervised pilot
- Command or source: ShopBridge redacted support diagnostics feature; smoke scripts in `scripts/`

## Evidence

When reporting a problem, a pilot merchant or test buyer should collect:

1. **Merchant diagnostics bundle** (redacted by design — safe to share):
   WordPress admin -> WooCommerce -> AgentCart -> support diagnostics. Attach
   the exported summary (readiness, registry, signed-request, verifier,
   sandbox-check, product exposure, and WooCommerce setup state).
2. **The failing identifiers**, not screenshots alone: merchant id, order id,
   merchant quote id, `quote_hash`, approval hash, `payment_contract_hash`,
   transaction/refund reference, and the timestamp (with timezone).
3. **The exact command or client** that failed: smoke script invocation,
   buyer-agent runtime (service / direct skill / MCP client) and tool call, or
   the admin action, plus the full error response body.
4. **For checkout/payment issues**: the smoke transcript, e.g.
   `python3 scripts/woocommerce-shopbridge-smoke.py --base-url <shop> --require-shipping`
   output, or the settlement smoke transcript.
5. **Never send**: bearer tokens, signed-request secrets, private keys, or
   `.secrets/` files. Diagnostics and ops events are already redacted; if raw
   logs are needed the maintainer will ask for a specific redacted excerpt.

Where to send: see `pilot/pilot-support-channel/support_contact.md`.
