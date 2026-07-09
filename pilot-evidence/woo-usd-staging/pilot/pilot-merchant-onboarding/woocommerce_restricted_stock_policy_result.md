# woocommerce_restricted_stock_policy_result

- Scope: `pilot_gate`
- Owner id: `pilot-merchant-onboarding`
- Recorded at: 2026-07-09T20:40Z
- Operator: Codex local verification session authorized by Max (GiraeffleAeffle)
- Command or source: `python3 scripts/check-woocommerce-compatibility-matrix.py --run-smoke --merchant-variance-profile restricted-stock-policy`

## Evidence

The fresh restricted-stock runtime smoke passed and cleaned up successfully.
The profile applied low managed stock, per-product maximum quantities, country
restrictions, restricted-goods policy, and soft stock holds; only three
products remained in the saved exposure snapshot. The permitted tea path still
returned a valid EUR quote of 1,480 cents with 490 cents shipping and one VAT
line, while the seeded blocked and restricted products remained outside the
eligible happy path. Manifest, registry, and quote contract checks all passed.
