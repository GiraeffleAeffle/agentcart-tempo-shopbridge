# WooCommerce merchant-variance pilot harness

GitHub issue: https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/19

## What to build

Extend the WooCommerce pilot verification path so the team can exercise at
least two materially different WooCommerce merchant setups before external
beta. The slice should make merchant variance explicit in the compatibility
matrix and document how to collect evidence from each setup.

## Acceptance criteria

- [ ] Compatibility or pilot docs define at least two distinct merchant variance
  profiles to run before beta.
- [ ] Each profile names the tax, shipping, stock, plugin, and checkout
  behaviors it is meant to stress.
- [ ] The harness command path can be run separately from the fast source-level
  tests.
- [ ] Pilot evidence docs name the expected result file for each merchant
  variance profile.
- [ ] The release decision flow treats missing variance evidence as an
  actionable pilot gap.

## Blocked by

None - can start immediately

## Slice metadata

Type: AFK
Source: Pilot Execution Readiness recommendation
