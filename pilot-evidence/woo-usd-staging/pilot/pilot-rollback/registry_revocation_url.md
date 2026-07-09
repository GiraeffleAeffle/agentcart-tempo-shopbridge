# registry_revocation_url

- Scope: `pilot_gate`
- Owner id: `pilot-rollback`
- Recorded at: 2026-07-05
- Operator: Max (GiraeffleAeffle), recorded via Claude Code session
- Command or source: `curl -o /dev/null -w '%{http_code}'` against the staging shop

## Evidence

- Revocation document URL for the staging merchant
  (`agentcart-usd-staging-shop`):
  `https://woo-usd.agentcart.eu/.well-known/agentcart-registry-revocations.json`
- Verified HTTP 200 on 2026-07-05.
- The matching registry bundle
  (`https://woo-usd.agentcart.eu/.well-known/agentcart-registry-bundle.json`,
  HTTP 200 on 2026-07-05) carries the revocation pointer, so registry loaders
  and buyer paths check it on verification.

When the external merchant joins the pilot, record their shop's revocation URL
in their evidence folder the same way.
