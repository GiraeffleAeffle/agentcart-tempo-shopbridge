# verifier_metrics_snapshot

- Scope: `pilot_gate`
- Owner id: `pilot-payment-mode`
- Recorded at: 2026-07-09T20:35Z
- Operator: Codex deployment session authorized by Max (GiraeffleAeffle)
- Command or source: authenticated internal `GET /metrics.json` inside the verifier container

## Evidence

Snapshot schema: `agentcart.verifierMetrics.v1`. Since container start, the
verifier recorded 41 requests and 41 responses: 41 successful, zero rejected,
and zero errors. Operations comprised 39 health checks, one payment, and one
refund. Both Tempo MPP rail operations succeeded; payment latency was 333 ms
and refund latency was 1,589 ms. Settlement counters recorded one verified
testnet settlement and one verified testnet refund. Provider errors were empty.
Replay storage was writable SQLite with 19 payment, 8 refund-request, and 8
refund claims; the required journal was writable with 35 entries and no error.
The alert webhook was explicitly unconfigured, so alert-delivery evidence
remains a separate blocker.

## Talos snapshot (2026-08-23)

The verifier process restarted as part of the persistence drill, so its
process-local request counters reset and are not presented as cumulative pilot
traffic. Persistent diagnostics are authoritative: one payment, one refund
request, one refund, and four replay-journal entries after the expected
conflict probe. The structured request log recorded that probe as
`status=409`, `outcome=rejected`, and `rejection_reason=replay_conflict`.

The immediately following alert event reported `state=skipped` and
`reason=no_verifier_alert_webhook_configured`. This is evidence that the
warning was generated, not that an alert receiver accepted it.
