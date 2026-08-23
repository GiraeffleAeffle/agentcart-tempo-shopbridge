# production_payment_profile_check_result

- Scope: `pilot_gate`
- Owner id: `pilot-payment-mode`
- Recorded at: 2026-07-09T20:34Z
- Operator: Codex deployment session authorized by Max (GiraeffleAeffle)
- Command or source: `python3 scripts/check-production-payment-profile.py --env-file .secrets/agentcart-staging-usd.env --deployment-profile hetzner-usd-staging`

## Evidence

The checker returned `production payment profile ok` without printing secret
values. The normalized Hetzner USD profile requires external-verifier-only
checkout, a deployment-pinned internal verifier, strong and separated merchant,
verifier, MPP, and signed-request credentials, required signed checkout,
durable SQLite replay storage, and a required replay journal. The same profile
was consumed by the evidence collector, where the production-payment-profile
gate passed with zero errors.

## Talos deployment confirmation (2026-08-23)

Command:

`python3 scripts/check-production-payment-profile.py --env-file .secrets/agentcart-staging-usd.env --deployment-profile talos-usd-staging`

The Talos profile passed and selects the actual cluster-local
`http://woo-usd-verifier:4260/agentcart/verify` boundary. The workload uses
secret references, runs the Tempo-only rail, and stores required replay state
on a Bound PVC. Live health and manifest checks confirmed the same fail-closed
settings without printing secret values. The older Hetzner profile remains
available only for rollback compatibility.
