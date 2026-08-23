# verifier_health_or_fixture_result

- Scope: `pilot_gate`
- Owner id: `pilot-payment-mode`
- Recorded at: 2026-07-09T20:34Z
- Operator: Codex deployment session authorized by Max (GiraeffleAeffle)
- Command or source: remote Docker health, verifier diagnostics, and strict Tempo MPP settlement fixture

## Evidence

After rollout, Docker reported the verifier container healthy with no published
host port. Authenticated internal diagnostics reported a writable durable
SQLite replay store with `error=null`, and the replay journal was writable with
no last error. The strict testnet fixture then verified one quote-bound payment
and one rail-bound refund. Post-run metrics reported 41 successful responses,
zero rejected responses, zero internal errors, and a 100 percent success rate.
The deployment and settlement details are recorded in
`attachments/usd-hardening-rollout-2026-07-09.md`.

## Talos health and live fixture (2026-08-23)

The Talos verifier pod is Ready with zero restarts and runs the pinned GHCR
digest as a non-root workload. Its 1 GiB PVC is Bound, and its NetworkPolicy
permits storefront ingress plus DNS/public-HTTPS egress only. Health reported
no missing or invalid configuration, Tempo settlement `verify`, Tempo refund
`live`, and durable writable SQLite replay state.

The live fixture verified one 1,578-cent pathUSD payment and one rail-bound
refund, survived a rollout restart with all replay counts intact, then rejected
a conflicting reuse with HTTP 409. Post-probe health remained `ok`.
