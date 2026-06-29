# Provider verifier operations readiness pack

GitHub issue: https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/18

## What to build

Add the provider-specific verifier operations pack needed before a supervised
external beta: dashboard requirements, alert requirements, backup/restore drill
evidence, and operator artifacts for the Stripe/card MPP verifier path. The
slice should make the verifier ops proof collectable by the pilot evidence
runner even before moving beyond the SQLite pilot store.

## Acceptance criteria

- [ ] Verifier operations docs name required health, metrics, replay-conflict,
  and provider-error signals.
- [ ] Backup and restore drill steps are documented for the pilot SQLite replay
  store.
- [ ] Alert thresholds and incident owner actions are captured for pilot
  operation.
- [ ] Pilot evidence docs name the expected verifier ops evidence files and
  report snippets.
- [ ] At least one focused check or test validates the operations pack
  references existing verifier health/metrics surfaces.

## Blocked by

None - can start immediately

## Slice metadata

Type: AFK
Source: Pilot Execution Readiness recommendation
