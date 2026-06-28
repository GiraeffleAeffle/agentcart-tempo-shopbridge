# Introduce approval and audit golden fixtures

## What to build

Add golden fixtures for Approval Record, approval decision, payment handoff, Audit Packet, audit import, and audit export so service-backed, skill-only, and generic MCP-style paths preserve the same hashes.

## Acceptance criteria

- [ ] Direct Skill and AgentCart Service produce matching approval hashes for the same Final Quote.
- [ ] Tampered Audit Packet fixture is rejected before network import.
- [ ] Imported skill-only Audit Packet is idempotent.
- [ ] Generic MCP example references the same required hashes.
- [ ] Buyer-agent matrix check validates fixture coverage.

## Blocked by

None - can start immediately.

## Slice metadata

Type: AFK
Source: `docs/PRODUCTION_ISSUE_SLICES.md`

