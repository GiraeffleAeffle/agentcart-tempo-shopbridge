# woocommerce_baseline_eu_tax_shipping_result

- Scope: `pilot_gate`
- Owner id: `pilot-merchant-onboarding`
- Recorded at: 2026-07-09T20:38Z
- Operator: Codex local verification session authorized by Max (GiraeffleAeffle)
- Command or source: `python3 scripts/check-woocommerce-compatibility-matrix.py --run-smoke --merchant-variance-profile baseline-eu-tax-shipping`

## Evidence

The fresh baseline EU runtime smoke passed and cleaned up successfully. It
seeded four exposed products, inclusive EU VAT, and taxable tracked-parcel
shipping. A German quote for Hazel's Chocolate Tea returned EUR currency,
1,480 cents total, 490 cents shipping, and one VAT line. The manifest and
registry bundle validated, the quote hash was present, and the compatibility
runner reported the matrix as valid after the live endpoint smoke completed.
