# Ubiquitous Language

## Commerce Core

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Merchant** | An opt-in WooCommerce shop that remains merchant of record for a purchase. | Seller, vendor, store |
| **ShopBridge Plugin** | The WooCommerce runtime that exposes agent-readable commerce surfaces for an opt-in Merchant. | AgentBridge, Woo plugin, merchant plugin |
| **AgentCart Service** | The optional buyer-side runtime for durable household policy, approval, audit, registry, and local integrations. | Gateway, server, backend |
| **Direct Skill** | The buyer-side skill-only runtime that calls verified ShopBridge Plugin surfaces without the AgentCart Service. | Buyer skill, Codex skill, skill-only mode |
| **Manifest** | The Merchant capability document at `/.well-known/agentcart.json`. | Capability document, discovery document |
| **Catalog** | Merchant-selected product data exposed for agent search and quote preparation. | Product feed, inventory feed |
| **Final Quote** | A WooCommerce-backed checkout contract binding items, destination, shipping, VAT, total, expiry, payment requirements, and quote hash. | Quote, estimate, cart total |
| **Approval Record** | The explicit buyer consent artifact bound to a Final Quote. | Approval, consent, mandate |
| **Payment Requirements** | The quote-bound rail and verifier requirements that a payment-capable agent must satisfy. | Payment profile, payment challenge |
| **Order** | A WooCommerce order created after quote, approval, idempotency, stock, drift, and payment verification checks pass. | Purchase, transaction |
| **Aftercare** | Structured post-checkout state covering fulfillment, delivery, cancellation, refund, support, and buyer messages. | Order status, support state |
| **Audit Packet** | A portable hash-linked evidence packet for skill-only approval, payment, checkout, and import/export events. | Audit log, evidence bundle |

## Trust And Settlement

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Registry Record** | A public identity and integrity record binding Merchant id, domain, manifest URL, claim hash, payment destination, proof, freshness, and revocation pointer. | Registry entry, merchant listing |
| **Registry Claim** | The stable manifest payload whose hash a Registry Record binds. | Manifest hash, proof hash |
| **Domain Proof** | Merchant-hosted proof that a Registry Record belongs to the claimed domain. | Signature, domain signature |
| **Revocation Document** | Merchant-hosted record showing which Registry Records should no longer be trusted. | Blocklist, denylist |
| **External Verifier** | The rail-specific authority that proves payment or refund evidence before real money movement is claimed. | Payment service, payment adapter |
| **Payment Contract Hash** | The hash binding the quote-level payment contract and verifier expectations. | Contract hash, payment hash |
| **Replay Reference** | A payment or refund reference that must be unique or exactly idempotent. | Transaction id, refund id |

## Relationships

- A **Merchant** publishes exactly one current **Manifest** per public ShopBridge installation.
- A **Registry Record** binds one **Merchant** domain to one **Manifest** URL and one **Registry Claim** hash.
- A **Catalog** item can produce many **Final Quotes**, but each **Final Quote** is consumed at most once for checkout.
- An **Approval Record** belongs to exactly one **Final Quote**.
- **Payment Requirements** belong to a **Final Quote**, not merely to a Merchant.
- An **Order** must preserve the **Final Quote**, **Approval Record**, **Payment Contract Hash**, and verifier evidence used to create it.
- An **Audit Packet** can be created by the **Direct Skill** and later imported into the **AgentCart Service**.

## Example Dialogue

> **Dev:** "Can the Direct Skill just pay from the Catalog result?"
>
> **Domain expert:** "No. The Catalog is untrusted product data. The buyer needs a Final Quote because shipping, VAT, stock, expiry, and Payment Requirements are quote-bound."
>
> **Dev:** "So the Approval Record should bind the Final Quote hash, not the product text?"
>
> **Domain expert:** "Exactly. The Order can only be created after the Approval Record and External Verifier evidence match that Final Quote."
>
> **Dev:** "And if the merchant changes shipping before checkout?"
>
> **Domain expert:** "Checkout fails with quote recovery, and the buyer agent requests a fresh Final Quote."

## Flagged Ambiguities

- "Gateway" can mean the **AgentCart Service**, the hosted registry gateway, or a general HTTP entry point. Prefer the precise term.
- "Payment profile" can mean merchant-wide rail configuration or quote-level **Payment Requirements**. Use **Payment Requirements** when the data is quote-bound.
- "Quote" is often used casually for both estimates and checkout contracts. Use **Final Quote** when approval or payment binding matters.
- "Approval" can mean the human decision or the stored artifact. Use **Approval Record** for the artifact and "approval decision" for the decision event.
- "Order status" is narrower than **Aftercare**. Use **Aftercare** when refund, cancellation, tracking, and support state are included.

