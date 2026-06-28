# Define one Aftercare state fixture set

## What to build

Create canonical Aftercare fixtures for unpaid demo state, paid order, delayed delivery, shipped tracking, cancellation requested, partial refund, verified refund, and refund failure. Use them to align ShopBridge Plugin, AgentCart Service, and Direct Skill buyer messages.

## Acceptance criteria

- [ ] Direct Skill aftercare summary never claims demo refund execution.
- [ ] Verified refund fixture clearly claims verifier-backed refund evidence.
- [ ] Carrier tracking and delivery exception fields are normalized.
- [ ] Cancellation state is distinct from refund state.
- [ ] Merchant-controlled policy text is marked untrusted in buyer-facing outputs.

## Blocked by

None - can start immediately.

## Slice metadata

Type: AFK
Source: `docs/PRODUCTION_ISSUE_SLICES.md`

