# registry_record_or_bundle_url

- Scope: `pilot_gate`
- Owner id: `pilot-merchant-onboarding`
- Recorded at: 2026-07-05T21:06Z
- Operator: Max (GiraeffleAeffle), recorded via Claude Code session
- Command or source: settlement smoke registry section plus `curl` HTTP checks

## Evidence

- Registry bundle URL:
  `https://woo-usd.agentcart.eu/.well-known/agentcart-registry-bundle.json`
  (HTTP 200 verified 2026-07-05).
- Revocation document URL:
  `https://woo-usd.agentcart.eu/.well-known/agentcart-registry-revocations.json`
  (HTTP 200 verified 2026-07-05).
- Manifest URL: `https://woo-usd.agentcart.eu/.well-known/agentcart.json`
  (HTTP 200 verified 2026-07-05).
- Registry record from the 2026-07-05 settlement smoke:
  merchant id `agentcart-usd-staging-shop`, record hash
  `ffb1229726e11493132530361ccadb50b2eca4917025636ec64c677425e6314c`.

Note: hosted-registry submission (`POST /v1/registry/records` on the alpha
gateway) is not part of this artifact; record it separately if the pilot uses
the hosted feed instead of the merchant-hosted bundle.
