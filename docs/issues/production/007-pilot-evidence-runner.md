# Pilot evidence runner

## What to build

Add a command that collects and validates the minimum external beta evidence folder for one merchant and all required buyer-agent runtime paths.

## Acceptance criteria

- [ ] Command runs the existing pilot, buyer-agent, payment-profile, and WooCommerce compatibility gates.
- [ ] Missing evidence produces actionable paths and gate ids.
- [ ] A sample evidence folder documents expected transcript names.
- [ ] Output is suitable to attach to a release decision.
- [ ] `verify.sh` can opt into the evidence runner through existing environment gates.

## Blocked by

- Blocked by #2.
- Blocked by #3.
- Blocked by #4.

## Slice metadata

Type: AFK
Source: `docs/PRODUCTION_ISSUE_SLICES.md`
