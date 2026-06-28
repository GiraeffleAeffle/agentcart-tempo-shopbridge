# Architecture Readiness Review

Status: adoption pass created from the current production-candidate alpha codebase.

This review uses the project terms in `CONTEXT.md` and the architecture terms module, interface, seam, adapter, depth, leverage, and locality. It is intentionally a candidate list, not a refactor plan. The next step is to pick one candidate and grill the design before changing code.

## Summary

The repo has strong production intent: contract docs, machine-readable matrices, verifier fixtures, release tooling, and many source-level tests. The main architecture risk is that several important domain modules are implemented as large files with broad interfaces:

- `gateway/agentcart.py` combines registry, quote tournament, approval, checkout, audit, aftercare, notification, rendering, and HTTP routing.
- `woocommerce-shopbridge/agentcart-shopbridge/agentcart-shopbridge.php` combines WordPress admin UI, REST routes, quote construction, stock holds, verifier calls, signed requests, registry publishing, aftercare, and serialization.
- `gateway/shopbridge-direct-skill/scripts/shopbridge-command.py` combines merchant resolution, registry verification, approval packet creation, payment handoff, quote discovery, checkout payload validation, and aftercare formatting.
- `household-os/household_os.py` combines task/calendar, Home Assistant, OpenClaw, AgentCart client, chat handling, and HTML rendering.

The tests are useful but skew toward contract/source assertions and pure unit checks. The highest production value now is to create deeper modules around the runtime seams that production will operate, monitor, and test.

## Deepening Opportunities

### 1. Final Quote And Checkout Integrity Module

**Files**

- `woocommerce-shopbridge/agentcart-shopbridge/agentcart-shopbridge.php`
- `gateway/agentcart.py`
- `docs/QUOTE_RELIABILITY.md`
- `woocommerce-shopbridge/tests/test_plugin_contracts.py`

**Problem**

Final Quote integrity is spread across quote hash payloads, money drift checks, stock holds, idempotency, payment contract hashes, and order creation. The interface a maintainer must understand is nearly as complex as the implementation. This reduces locality for bugs around expired quotes, drift, stock conflicts, and replayed checkout.

**Solution**

Create a deeper Final Quote and checkout integrity module in the ShopBridge Plugin. It should own quote hash payload construction, quote recovery errors, live quote revalidation, quote locks, stock-hold confirmation/release, and the exact data that order creation is allowed to consume.

**Benefits**

- Locality: quote drift and checkout safety fixes land in one module.
- Leverage: endpoint handlers, sandbox checkout, smoke tests, and future integration tests use the same interface.
- Test improvement: WordPress/WooCommerce integration tests can exercise the same module through quote and order endpoints instead of asserting scattered source snippets.

### 2. External Verifier Client Module

**Files**

- `woocommerce-shopbridge/agentcart-shopbridge/agentcart-shopbridge.php`
- `gateway/scripts/stripe-mpp-verifier.mjs`
- `docs/VERIFIER_CONTRACT.md`
- `docs/fixtures/verifier/`

**Problem**

Payment verification, refund verification, verifier HTTP hardening, redacted errors, and replay semantics are production-critical, but the ShopBridge Plugin currently exposes them as private helpers inside a very large class. The seam between commerce and rail-specific verification exists conceptually but is shallow in the code.

**Solution**

Extract an External Verifier client module for request construction, redirect-safe HTTP calls, response validation, redaction, and error classification. Keep rail-specific proof execution outside ShopBridge; this module should only enforce the verifier contract from the merchant side.

**Benefits**

- Locality: verifier security and error handling changes are isolated.
- Leverage: payment and refund endpoints, sandbox tests, and production smoke can reuse one contract surface.
- Test improvement: negative verifier fixtures can drive module-level tests plus endpoint-level integration tests.

### 3. Merchant Registry Trust Module

**Files**

- `gateway/agentcart.py`
- `gateway/shopbridge-direct-skill/scripts/shopbridge-command.py`
- `gateway/scripts/registry_record.py`
- `docs/MERCHANT_REGISTRY.md`
- `gateway/tests/test_registry_record_tool.py`
- `gateway/tests/test_shopbridge_direct_skill.py`

**Problem**

Registry verification logic exists in the AgentCart Service, Direct Skill, and registry tooling. Similar concepts appear in multiple places: claim binding, domain proof, endpoint scope, payment binding, freshness, revocation, and optional onchain identity metadata. This duplicates trust rules across runtime paths.

**Solution**

Create a shared Merchant Registry trust module, or at minimum a shared executable contract fixture suite, that both the AgentCart Service and Direct Skill consume. Keep runtime-specific fetching and output formatting outside the module.

**Benefits**

- Locality: trust-rule changes do not need parallel edits in service, skill, and tooling.
- Leverage: future append-only or onchain registry adapters can reuse the same verification interface.
- Test improvement: the same positive and negative registry cases can run against every adapter.

### 4. Approval And Audit Evidence Module

**Files**

- `gateway/agentcart.py`
- `gateway/shopbridge-direct-skill/scripts/shopbridge-command.py`
- `docs/BUYER_AGENT_TEST_MATRIX.md`
- `gateway/tests/test_agentcart.py`
- `gateway/tests/test_shopbridge_direct_skill.py`

**Problem**

Approval Record, approval packet, approval decision, payment handoff, audit packet, audit import, and audit export are central to buyer trust. Their hashes must stay consistent across service-backed and skill-only paths, but they are implemented in separate files with parallel helper functions.

**Solution**

Create a deeper approval and audit evidence module that owns canonical payloads and hashes for Approval Record, approval decision, payment handoff evidence, Audit Packet, audit import validation, and audit export hashing.

**Benefits**

- Locality: hash-shape changes are made once.
- Leverage: all buyer-agent runtimes can preserve the same evidence model.
- Test improvement: cross-runtime golden fixtures can verify service, direct skill, and generic MCP paths.

### 5. Aftercare State Module

**Files**

- `woocommerce-shopbridge/agentcart-shopbridge/agentcart-shopbridge.php`
- `gateway/agentcart.py`
- `gateway/shopbridge-direct-skill/scripts/shopbridge-command.py`
- `docs/DELIVERY_AND_REFUNDS.md`

**Problem**

Aftercare includes fulfillment tracking, cancellation eligibility, refund policy, refund evidence, buyer messages, and delivery exceptions. The logic appears in merchant, service, and direct-skill paths. The risk is inconsistent buyer messaging, especially around demo refunds versus verifier-backed real refunds.

**Solution**

Define one Aftercare state model and build adapters around it: ShopBridge Plugin serializes source state, AgentCart Service stores and refreshes it, and Direct Skill formats it for the buyer. Avoid letting each runtime invent its own money/refund wording.

**Benefits**

- Locality: refund-safe messaging and lifecycle rules are concentrated.
- Leverage: carrier adapters and refund state machines can plug into one state model.
- Test improvement: one fixture set can assert buyer messages never claim real money movement without verifier evidence.

### 6. Household Integration Facade

**Files**

- `household-os/household_os.py`
- `household-os/tests/test_household_os.py`

**Problem**

Household OS mixes Vikunja, Home Assistant, OpenClaw, AgentCart client calls, chat behavior, calendar rendering, and HTML views. The module is workable for a demo, but future production hardening will need clearer locality around what is household policy, what is integration plumbing, and what is UI formatting.

**Solution**

Split the household runtime around existing adapters: task/calendar, Home Assistant, AgentCart commerce client, chat orchestration, and rendering. Start only where there are two real adapters or where tests currently need to cross too much unrelated behavior.

**Benefits**

- Locality: integration failures and policy behavior are easier to reason about separately.
- Leverage: non-technical setup and support diagnostics can reuse the same integration checks.
- Test improvement: household workflows can be tested without constructing every integration at once.

## Recommended First Candidate

Start with the External Verifier client module or the Final Quote and checkout integrity module. They sit on the highest-risk production path: paid order creation and refunds. They also have existing contract docs and fixtures, so the test surface is already clear.

