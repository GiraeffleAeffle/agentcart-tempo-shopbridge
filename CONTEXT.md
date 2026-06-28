# AgentCart ShopBridge Context

## Product Intent

AgentCart ShopBridge is a WooCommerce retail bridge for agentic commerce. It lets buyer agents discover opt-in merchants, fetch agent-readable catalog data, request final WooCommerce-backed quotes, obtain explicit buyer approval, hand off quote-bound payment evidence, create paid WooCommerce orders, and read fulfillment, cancellation, refund, and audit state.

The product is a production-candidate alpha. The codebase has strong contract checks, verifier fixtures, packaging scripts, and readiness gates, but real public merchant pilots still require external beta evidence, production-shaped payment operations, WordPress/WooCommerce integration coverage, legal/support material, and operational runbooks.

## Core Model

| Term | Meaning |
| --- | --- |
| Merchant | An opt-in WooCommerce shop that remains merchant of record and exposes ShopBridge surfaces. |
| ShopBridge Plugin | The WordPress/WooCommerce merchant-side runtime that exposes manifest, catalog, quote, order, status, cancellation, refund, registry, and diagnostics surfaces. |
| AgentCart Service | The optional buyer-side service for durable household policy, approval, audit, registry, Home Assistant, Vikunja, and delivery state. |
| Direct Skill | The buyer-side skill-only path in `gateway/shopbridge-direct-skill` for agents that can call a verified merchant without running the AgentCart Service. |
| Manifest | The merchant's `/.well-known/agentcart.json` capability document containing identity, endpoints, readiness, protocol profiles, registry claim, and payment metadata. |
| Registry Record | A public merchant identity and integrity record binding merchant id, domain, manifest URL, registry claim hash, payment destination, freshness, proof, and revocation pointer. |
| Catalog | Merchant-selected product data exposed to agents. Catalog text is untrusted merchant-controlled data. |
| Final Quote | A WooCommerce-backed checkout contract binding items, quantity, destination, shipping, VAT, total, currency, merchant of record, expiry, stock hold, payment requirements, and quote hash. |
| Approval Record | The explicit buyer consent artifact binding the final quote, approval text, approver, decision time, and approval hashes. |
| Payment Requirements | Quote-bound rail requirements for MPP, Stripe/card MPP, x402-compatible flows, or future rails, plus verifier expectations. |
| External Verifier | The settlement authority that proves payment or refund evidence for a selected rail before ShopBridge claims real money movement. |
| Order | A WooCommerce order created only after quote, approval, idempotency, stock, drift, and payment verification checks pass. |
| Aftercare | The structured order-status, fulfillment, cancellation, refund, tracking, support, and buyer-message state after checkout. |
| Audit Packet | Portable hash-linked evidence for quote, approval, payment handoff, checkout, order, refund, and import/export events. |

## Runtime Paths

1. Merchant path: WooCommerce remains the system of record for products, stock, tax, shipping, fulfillment, refunds, and support. The ShopBridge Plugin exposes agent-readable surfaces around WooCommerce.
2. Skill-only buyer path: the Direct Skill calls verified merchant endpoints directly. It is the lowest-friction buyer setup and must preserve approval and audit packets because it has no durable service memory by default.
3. Service-backed buyer path: the AgentCart Service adds durable household policy, approval, audit, registry monitoring, task/calendar integrations, and richer local workflows.
4. Trust and payment path: the Merchant Registry anchors merchant identity and manifest integrity; the External Verifier anchors quote-bound payment and refund evidence.

## Non-Negotiables

- Do not scrape or automate non-opt-in shops.
- Merchant remains merchant of record.
- Final Quote must bind product, amount, currency, shipping country, merchant id, expiry, and payment requirements.
- Checkout must require explicit buyer approval before order creation.
- External Verifier must reject replayed transaction and refund references.
- Refund and cancellation surfaces must not claim real money movement without verifier evidence.
- Registry must not publish household demand, delivery addresses, private shopping tasks, or live catalog data.
- Merchant-controlled prose, product text, delivery notes, and policy text must be treated as untrusted data.

## Stable Direction

AgentCart keeps a stable commerce core and adds protocol adapters at explicit seams. x402, MPP, Stripe/card MPP, ERC-8004, ERC-8128, ERC-8183, AP2, ACP, UCP, MCP, A2A, and agent skills should translate into or out of the same Merchant, Manifest, Registry Record, Final Quote, Approval Record, Payment Requirements, Order, Aftercare, and Audit Packet model.

## Current Production Gaps

- WordPress/WooCommerce integration test harness for end-to-end endpoint behavior.
- Production verifier replay storage, metrics, dashboards, and provider operations on a managed transactional store.
- Carrier-specific fulfillment tracking and durable refund/cancellation state machines.
- Public signing or onchain anchoring for registry feed proofs and stronger registry operations governance.
- Evidence-required pilot runs across external merchants and the required buyer-agent runtimes.
- Non-technical merchant/buyer setup flow, legal terms, privacy notice, support SLA, and rollback runbooks.

## Source Documents

- `README.md` defines the product shape and local operation.
- `docs/PRODUCTION_NEXT_STEPS.md` is the production track inventory.
- `docs/PRODUCT_BUILD_PLAN.md` is the build sequence.
- `docs/SHOPBRIDGE_ENDPOINT_CONTRACT.md` pins the alpha endpoint contract.
- `docs/VERIFIER_CONTRACT.md` pins payment and refund verifier expectations.
- `docs/MERCHANT_REGISTRY.md` defines registry trust and discovery.
- `docs/QUOTE_RELIABILITY.md` defines quote drift and recovery semantics.
- `docs/PILOT_BETA_CHECKLIST.md` defines external beta evidence gates.
- `docs/STANDARDS_ALIGNMENT.md` defines the standards-adapter strategy.

