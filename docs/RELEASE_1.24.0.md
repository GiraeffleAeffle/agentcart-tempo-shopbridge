# AgentCart 1.24.0 — Staging preflight and scheduled recovery

This release helps maintainers run supervised staging sessions without relying
on shop traffic to recover interrupted operations. It does not approve a paid
production launch or supply an independently verified merchant registry.

## Changes

- A read-only tester preflight checks fresh manager/verifier diagnostics,
  matching versions and four release artifacts, staging/test payment settings,
  signed mutations, encrypted transactional recovery, durable payment storage,
  scheduler heartbeats and outstanding cases. Output omits input identifiers,
  credentials and customer/provider details. See [onboarding](TESTER_ONBOARDING.md).
- The Helm shop runs due WordPress jobs in a restricted scheduler container.
  Manager diagnostics expose heartbeat, unresolved age and exhausted retries.
  Recovery scans support both legacy and HPOS storage and avoid starving new
  eligible work behind exhausted cases. Existing manager authorization remains
  necessary before starting compensation.
- The verifier can reconcile existing authorized refunds with durable leases,
  backoff and an eight-attempt budget. It preserves Stripe provider identities
  and Tempo signed transactions, checks current configuration against persisted
  bindings, and uses the existing throttled alert channel for stuck refunds.
- Verifier health reports the release version, credential mode and allowed
  Tempo networks. The chart defaults to testnet only; direct verifier deployments
  retain the previous network support unless explicitly restricted.
- Plugin, gateway, both charts and all three skill packages move to 1.24.0.
  Buyer model selection remains Codex/Astra through the Direct Skill.

## Upgrade

Back up the Woo database and original WordPress auth salts together, and preserve
the verifier SQLite database and replay journal. Inspect unresolved operations
before enabling either worker: enabling reconciliation resumes previously
requested refunds and recovery. Install matching plugin/skill ZIPs and pin the
new published verifier image digest. The chart enables the scheduler and refund
reconciliation; non-Helm deployments enable the verifier worker with
`AGENTCART_REFUND_RECONCILIATION_ENABLED=true` and restrict staging networks with
`AGENTCART_VERIFIER_ALLOWED_TEMPO_NETWORKS=testnet`.

The verifier adds a reconciliation side table; existing payment/refund evidence
is retained. To roll back, stop new checkout and both workers, reconcile pending
provider operations, then restore the previous application artifacts while
keeping current durable ledgers. Do not restore stale payment ledgers with writes
enabled. A SQLite fixture backup test is not a full disaster-recovery rehearsal.

## Validation and remaining work

Automated tests cover exclusive leases across processes, stale lease completion,
restart/backoff/exhaustion, and lost Stripe acknowledgements across SQLite
backup/restore using a fake provider. Real WooCommerce database fixtures cover
legacy and HPOS recovery, manager-approved compensation, repeated ticks,
scheduling fairness and contention for the last stock unit. Preflight tests
cover malformed/missing/stale diagnostics, live credentials, mixed networks,
expired admission, unresolved operations and redaction.

Still required: coordinated Woo/verifier restore drills with provider history,
real provider sandbox exercises, broader merchant/plugin compatibility, a fresh
buyer-agent evaluation, reviewed v2 deployment and independent validators,
security review and funded buyer protection before paid public use. Registry
bonds do not insure unlimited turnover; low prices are not grounds for slashing.
See [the remaining readiness work](TESTER_READINESS.md).
