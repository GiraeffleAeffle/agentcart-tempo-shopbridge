# provider_error_review

- Scope: `pilot_gate`
- Owner id: `pilot-payment-mode`
- Recorded at: 2026-07-09T20:35Z
- Operator: Codex deployment session authorized by Max (GiraeffleAeffle)
- Command or source: authenticated verifier metrics review after the strict MPP payment/refund smoke

## Evidence

The post-settlement verifier metrics contained an empty `provider_errors`
object, zero rejected outcomes, and zero error outcomes. The one Tempo MPP
payment and one Tempo refund both returned HTTP 200 and were counted as
successful. The replay journal reported no last error and the replay store
reported no error. Therefore no provider incident was opened for this rollout.
This is a review of the 2026-07-09 deployment window only; later provider
failures must be reviewed from their correlation id, provider error class, and
redacted verifier event.

## Talos review (2026-08-23)

Public RPC receipts independently confirmed that both the payment and refund
transactions succeeded with the expected 15,780,000-unit pathUSD transfer.
The live harness also recorded the intended 409 expired-quote and quote-hash
mismatch responses plus a 400 missing refund-idempotency response. A separate
conflicting transaction-reference probe returned the intended HTTP 409
`replay_conflict`; it is a policy rejection, not a provider incident. Health
remained `ok` with one claim in each replay bucket.

The replay warning generated a structured alert event, but delivery state was
`skipped` because no webhook is configured. That remains tracked separately as
an operations blocker.
