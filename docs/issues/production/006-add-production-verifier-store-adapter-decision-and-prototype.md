# Add production verifier store adapter decision and prototype

## What to build

Choose the production replay store for the External Verifier and build a narrow prototype that enforces transactional uniqueness for payment transaction references, refund requested references, and refund references.

## Acceptance criteria

- [ ] ADR records selected store and operational ownership.
- [ ] Prototype exposes health and metrics equivalent to the current sandbox verifier.
- [ ] Replay conflicts are rejected under concurrent requests.
- [ ] Migration path from lockfile sandbox store is documented.
- [ ] Dashboard/alert requirements are captured for the pilot operator.

## Blocked by

- Blocked by #1.

## Slice metadata

Type: HITL
Source: `docs/PRODUCTION_ISSUE_SLICES.md`
