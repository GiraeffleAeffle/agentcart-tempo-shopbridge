# catalog_preview_export

- Scope: `pilot_gate`
- Owner id: `pilot-merchant-onboarding`
- Recorded at: 2026-07-09T20:34Z
- Operator: Codex deployment session authorized by Max (GiraeffleAeffle)
- Command or source: `GET https://woo-usd.agentcart.eu/wp-json/agentcart/v1/catalog?search=tea`

## Evidence

The public catalog search returned exactly one matching exposed product:
`woo_10`, SKU `AGENT-TEA-HAZEL`, title `Hazel's Chocolate Tea`, currency USD,
and unit price 1,078 cents. Its structured AgentCart policy reports
`blocked=false` and `max_quantity=20`. The capability readiness snapshot
reports four AgentCart-enabled products under manual exposure, confirming that
the catalog is an explicit opt-in surface rather than a scrape of all products.
