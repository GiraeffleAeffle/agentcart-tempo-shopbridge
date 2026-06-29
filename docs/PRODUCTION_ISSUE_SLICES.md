# Production Issue Slices

Status: created as GitHub issues. These are intentionally written as independently grabbable tracer bullets.

GitHub issue bodies are mirrored in `docs/issues/production/`.

| Slice | GitHub issue |
| --- | --- |
| Extract Merchant-Side External Verifier Client | https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/1 |
| Add WordPress/WooCommerce Endpoint Integration Harness | https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/2 |
| Unify Registry Verification Fixtures Across Service And Direct Skill | https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/3 |
| Introduce Approval And Audit Golden Fixtures | https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/4 |
| Define One Aftercare State Fixture Set | https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/5 |
| Merchant Rollback And Revocation Runbook | https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/6 |
| Add Production Verifier Store Adapter Decision And Prototype | https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/7 |
| Pilot Evidence Runner | https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/8 |

## Pilot Execution Readiness Batch

Status: created as GitHub issues. These slices move the repo from structural
readiness checks to supervised external-beta operation.

GitHub issue bodies are mirrored in `docs/issues/pilot-execution/`.

| Slice | GitHub issue |
| --- | --- |
| Pilot execution playbook and dry-run evidence package | https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/17 |
| Provider verifier operations readiness pack | https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/18 |
| WooCommerce merchant-variance pilot harness | https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/19 |
| Non-maintainer merchant setup walkthrough | https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/20 |
| External beta go/no-go release decision | https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/21 |

## Slice 1: Extract Merchant-Side External Verifier Client

**Type:** AFK

**Blocked by:** None

## What to build

Move ShopBridge payment/refund verifier request construction, redirect-safe HTTP calls, response validation, and redacted error handling into a dedicated merchant-side module while preserving the current REST endpoint behavior.

## Acceptance criteria

- [ ] Payment and refund endpoints still pass the existing verifier contract tests.
- [ ] Verifier HTTP redirects remain rejected.
- [ ] Error responses remain redacted and structured.
- [ ] Existing positive and negative verifier fixtures still validate.
- [ ] A focused module-level test covers payment success, refund success, replay conflict, and redacted verifier failure.

## Slice 2: Add WordPress/WooCommerce Endpoint Integration Harness

**Type:** AFK

**Blocked by:** None

## What to build

Add a repeatable integration test harness that boots the local WordPress/WooCommerce stack and exercises the ShopBridge manifest, catalog, quote, checkout, status, refund, cancellation, and rate-limit surfaces through HTTP.

## Acceptance criteria

- [ ] Harness can run locally from a documented command.
- [ ] Quote totals are compared against WooCommerce cart totals.
- [ ] Checkout rejects expired quotes and quote hash mismatch.
- [ ] Refund endpoint requires idempotency and verifier evidence.
- [ ] Cancellation endpoint never claims refund execution.
- [ ] The harness can be gated separately from fast source-level tests.

## Slice 3: Unify Registry Verification Fixtures Across Service And Direct Skill

**Type:** AFK

**Blocked by:** None

## What to build

Create shared registry trust fixtures that assert claim binding, domain proof, endpoint scope, payment binding, freshness, revocation, and onchain identity metadata behavior across the AgentCart Service, Direct Skill, and registry tool.

## Acceptance criteria

- [ ] Same positive registry fixture is accepted by service, direct skill, and registry tool.
- [ ] Same negative fixtures are rejected consistently before catalog or quote calls.
- [ ] Revoked and stale records produce machine-readable reasons.
- [ ] Tests prove public HTTP registry feeds are rejected before fetching.
- [ ] Docs name the shared trust contract and its fixture location.

## Slice 4: Introduce Approval And Audit Golden Fixtures

**Type:** AFK

**Blocked by:** None

## What to build

Add golden fixtures for Approval Record, approval decision, payment handoff, Audit Packet, audit import, and audit export so service-backed, skill-only, and generic MCP-style paths preserve the same hashes.

## Acceptance criteria

- [ ] Direct Skill and AgentCart Service produce matching approval hashes for the same Final Quote.
- [ ] Tampered Audit Packet fixture is rejected before network import.
- [ ] Imported skill-only Audit Packet is idempotent.
- [ ] Generic MCP example references the same required hashes.
- [ ] Buyer-agent matrix check validates fixture coverage.

## Slice 5: Define One Aftercare State Fixture Set

**Type:** AFK

**Blocked by:** None

## What to build

Create canonical Aftercare fixtures for unpaid demo state, paid order, delayed delivery, shipped tracking, cancellation requested, partial refund, verified refund, and refund failure. Use them to align ShopBridge Plugin, AgentCart Service, and Direct Skill buyer messages.

## Acceptance criteria

- [ ] Direct Skill aftercare summary never claims demo refund execution.
- [ ] Verified refund fixture clearly claims verifier-backed refund evidence.
- [ ] Carrier tracking and delivery exception fields are normalized.
- [ ] Cancellation state is distinct from refund state.
- [ ] Merchant-controlled policy text is marked untrusted in buyer-facing outputs.

## Slice 6: Add Production Verifier Store Adapter Decision And Prototype

**Type:** HITL

**Blocked by:** #1

## What to build

Choose the production replay store for the External Verifier and build a narrow prototype that enforces transactional uniqueness for payment transaction references, refund requested references, and refund references.

## Acceptance criteria

- [ ] ADR records selected store and operational ownership.
- [ ] Prototype exposes health and metrics equivalent to the current sandbox verifier.
- [ ] Replay conflicts are rejected under concurrent requests.
- [ ] Migration path from lockfile sandbox store is documented.
- [ ] Dashboard/alert requirements are captured for the pilot operator.

## Slice 7: Pilot Evidence Runner

**Type:** AFK

**Blocked by:** #2, #3, #4

## What to build

Add a command that collects and validates the minimum external beta evidence folder for one merchant and all required buyer-agent runtime paths.

## Acceptance criteria

- [ ] Command runs the existing pilot, buyer-agent, payment-profile, and WooCommerce compatibility gates.
- [ ] Missing evidence produces actionable paths and gate ids.
- [ ] A sample evidence folder documents expected transcript names.
- [ ] Output is suitable to attach to a release decision.
- [ ] `verify.sh` can opt into the evidence runner through existing environment gates.

## Slice 8: Merchant Rollback And Revocation Runbook

**Type:** AFK

**Blocked by:** None

## What to build

Create and validate a production rollback runbook covering plugin deactivation, registry revocation, gateway release rollback, pilot product disabling, and audit preservation.

## Acceptance criteria

- [ ] Runbook names commands and responsible operator actions.
- [ ] Registry revocation path is tested against the hosted registry alpha endpoint.
- [ ] Plugin uninstall policy is confirmed to preserve commerce audit metadata.
- [ ] Pilot checklist links to the rollback runbook.
- [ ] Release docs link to the rollback runbook.
