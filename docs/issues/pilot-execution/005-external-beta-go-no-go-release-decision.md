# External beta go/no-go release decision

GitHub issue: https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/21

## What to build

Produce the first supervised external beta go/no-go decision using the pilot
evidence runner output, verifier operations evidence, WooCommerce variance
evidence, and merchant walkthrough findings. This slice is HITL because it
requires actual staging merchant evidence and an operator decision.

## Acceptance criteria

- [ ] The pilot evidence runner report is attached to the decision record.
- [ ] The decision explicitly lists passed gates, failed gates, accepted risks,
  and blockers.
- [ ] Verifier operations, WooCommerce variance, and merchant walkthrough
  evidence are referenced from the decision.
- [ ] If the decision is no-go, follow-up issues are filed for every blocking
  gap.
- [ ] If the decision is go, release docs identify the exact beta scope,
  rollback owner, support channel, and observation window.

## Tooling support

`scripts/build-beta-release-decision.py` generates the decision record from
`pilot-evidence-report.json`. It lists passed gates, failed gates, blockers,
accepted risks, follow-up issues, and the verifier operations, WooCommerce
variance, and merchant walkthrough evidence references.

The helper is intentionally stricter than a handwritten note:

- `--decision go` requires a passed evidence report plus `--beta-scope`,
  `--rollback-owner`, `--support-channel`, and `--observation-window`.
- `--decision no-go` with failed gates requires follow-up issue URLs or blocker
  owners.

This does not complete the issue by itself. The remaining work is to run the
real staging pilot, attach the generated report, and record the operator
decision.

## Blocked by

- Blocked by #17
- Blocked by #18
- Blocked by #19
- Blocked by #20

## Slice metadata

Type: HITL
Source: Pilot Execution Readiness recommendation
