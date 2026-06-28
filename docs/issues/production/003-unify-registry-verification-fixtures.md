# Unify registry verification fixtures across service and Direct Skill

## What to build

Create shared registry trust fixtures that assert claim binding, domain proof, endpoint scope, payment binding, freshness, revocation, and onchain identity metadata behavior across the AgentCart Service, Direct Skill, and registry tool.

## Acceptance criteria

- [ ] Same positive registry fixture is accepted by service, direct skill, and registry tool.
- [ ] Same negative fixtures are rejected consistently before catalog or quote calls.
- [ ] Revoked and stale records produce machine-readable reasons.
- [ ] Tests prove public HTTP registry feeds are rejected before fetching.
- [ ] Docs name the shared trust contract and its fixture location.

## Blocked by

None - can start immediately.

## Slice metadata

Type: AFK
Source: `docs/PRODUCTION_ISSUE_SLICES.md`

