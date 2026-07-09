# sandbox_quote_check_result

- Scope: `pilot_gate`
- Owner id: `pilot-merchant-onboarding`
- Recorded at: 2026-07-09T20:29Z
- Operator: Codex deployment session authorized by Max (GiraeffleAeffle)
- Command or source: strict USD release gate and Tempo MPP settlement smoke

## Evidence

The post-deployment quote check selected `woo_10` for delivery to New York and
returned a final quote of 1,578 cents USD: 1,078 cents product total plus 500
cents shipping, with one tax/VAT line. The settlement run bound quote hash
`e4cce9c39be18d614cd816b246bd3dff5df3324646d3a5f01745b5468a8caa16`
to payment contract hash
`230ea41e82a2635dfdc7a3db0749bca784bfeed423d0e836aa06b2121e694c1d`.
The strict release gate exited successfully and confirmed all production setup
steps before the mutable checkout test began.
