# agentcart_settings_readiness_snapshot

- Scope: `pilot_gate`
- Owner id: `pilot-merchant-onboarding`
- Recorded at: 2026-07-09T20:34Z
- Operator: Codex deployment session authorized by Max (GiraeffleAeffle)
- Command or source: live ShopBridge capability document after the Hetzner hardening rollout

## Evidence

`https://woo-usd.agentcart.eu/wp-json/agentcart/v1/capability` returned a stable
merchant id of `agentcart-usd-staging-shop`, `production_ready=true`, no
production blockers, and all six production setup steps complete. The shop
publishes `merchant@agentcart.eu`, public terms and returns URLs, four enabled
products, and manual product exposure. Payment configuration reports
`external_verifier_only`, `verifier_trust_mode=pinned_internal`, and an active
deployment-managed internal verifier pin. No credential values are present in
the capability response.
