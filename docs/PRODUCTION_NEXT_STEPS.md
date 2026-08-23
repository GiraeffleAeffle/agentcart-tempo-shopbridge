# AgentCart Production Tracks

> Status: production-candidate alpha with explicit production gaps. Public
> staging discovery is live for installability feedback, but paid production
> transactions are not enabled. This document separates implemented
> capabilities from the remaining gates required before paid merchant pilots.

This file turns the production roadmap into concrete engineering tracks.
Production use requires the remaining items below.

The standards direction is tracked in `docs/STANDARDS_ALIGNMENT.md`: AgentCart
keeps a stable commerce core and adds adapters for x402/MPP, ERC-8004,
ERC-8128, ERC-8183, AP2, ACP, UCP, MCP, and A2A at explicit seams.

## Status Summary

| Track | Current state | Production target | Next implementation slice |
| --- | --- | --- | --- |
| WooCommerce plugin hardening | Demo-capable ShopBridge plugin with catalog, quote, order, status, refund metadata, verifier hook, admin-configurable stable merchant id, local credential generation/rotation actions, signed-request key rotation with retiring-key revocation, admin readiness checks plus a guided setup checklist and plain-language merchant setup explainer, WordPress readme/uninstall packaging metadata, WordPress.org package/review-risk guards, strict PHPCS/WPCS and Plugin Check gates, semantic-release GitHub Release artifact publishing, baseline REST rate limits, idempotent order creation, single-use quote locking, merchant-controlled product exposure modes including category mode, admin exposure preview, saved catalog snapshot diffs, category blocklist, restricted-goods default blocking with explicit per-product allow override, product-level max quantity, checkout exclusion override, product shipping-country overrides, soft quote stock holds, stale quote recovery for expiry, stock, price, shipping, and tax drift, a checked quote reliability matrix, a fail-closed hard stock reservation adapter contract, structured restricted-goods metadata, structured item commerce-policy metadata with explicit product aftercare overrides, store-level aftercare policy defaults, sandbox quote and approval-bound checkout tests, redacted merchant support diagnostics, persisted approval hashes on WooCommerce orders, merchant-approved cancellation endpoint that never executes refunds, a frozen alpha ShopBridge endpoint contract, a repeatable demo reset command, and a checked Woo/PHP/WordPress compatibility matrix with a runnable Docker smoke entry | Installable merchant plugin with strict auth, idempotency, replay protection, richer product controls, privacy defaults, tests | Add WordPress/Woo integration tests, fulfillment-aware cancellation state machine, provider-specific hard stock reservation adapters, i18n, WordPress.org release assets, and host-level WAF guidance |
| Standards alignment | AgentCart has a stable commerce core, MPP-shaped checkout, merchant registry/domain proof, rail-neutral verifier contract, skill-only buyer path, audit import/export, registry transparency state, optional ERC-8004-style identity mapping metadata, configured-only manifest protocol profiles, an x402 exact-payment compatibility shim, MCP-style tool schemas, AP2-style unsigned checkout/payment mandate mappings, UCP-style checkout mappings, A2A-style handoff profile mappings, and an HMAC/RSA signed-request alpha seam with active signer metadata and key rotation | Standards-ready retail profile with adapters for x402/MPP payments, ERC-8004 identity, ERC-8128 signed HTTP requests, signed AP2/ACP/UCP/A2A clients, and ERC-8183 custom jobs | Add native UCP/A2A protocol runtime adapters and a signed AP2 runtime adapter when a concrete conformance target is selected |
| Stripe/card, Tempo/USD, and EUR settlement | The external verifier contract, positive/negative payment and refund fixtures, public-URL guard, structured logs/metrics/alerts, and fail-closed SQLite replay store are implemented. The pinned non-root verifier image is published to GHCR with provenance and an SBOM, and the Helm workload supports a Tempo-only USD profile without requiring Stripe configuration, persistent replay state, secret references, and restricted network policy. The image is live as the registry indexer runtime, but the USD verifier workload and payment/refund evidence are still pending. | External verifier validates real Stripe/card credentials or Tempo/x402 token transfers, executes settlement/refunds, binds results to the final quote, and survives restart without losing replay protection. | Deploy the published digest as the USD verifier profile, then record payment, refund, replay rejection, and persistent-volume restart evidence before adding EUR rails. |
| Merchant discovery registry | One shared trust module now enforces stable claims, controller-bound domain proof, endpoint scope, payment binding, freshness, revocation, and onchain identity across the gateway, Direct Skill, and registry helper. A shared projection replays complete contract lifecycle events from a finalized envelope, retains immutable historical record hashes for revocation/recovery, and fails closed. Chart 0.3.0 is live on the public registry with two least-privilege recurring indexer sidecars pinned by digest; it atomically serves only complete finalized snapshots and exposes immutable record documents. The Direct Skill discovers and verifies the same-origin onchain feed automatically. The v1 contract is deployed empty on Tempo Moderato as a trusted-operator testnet pilot. | Public identity/integrity registry with no private demand or catalog data on-chain, replaceable indexers, independently reproducible finalized state, and production governance. | After the hardened USD deployment, register the prepared merchant, wait for finalized state, prove buyer discovery, revoke it, recover with a new hash, and save the complete lifecycle evidence. |
| Delivery tracking/refunds | Woo status endpoint returns merchant-estimated delivery plus a normalized tracking adapter contract for Woo Shipment Tracking, AfterShip-style, ParcelPanel-style, and generic order meta; delayed, failed, returned, and partial-delivery carrier exceptions now update aftercare and calendar state; refund endpoint records verifier-backed provider refund references and rejects non-real verifier responses; aftercare normalizes cancellable, locked, cancelled-refund-required, partially refunded, and refunded lifecycle states; Woo, AgentCart service, and the direct skill generate buyer aftercare messages from structured state without claiming money returned unless real refund evidence is verified | Carrier API polling/webhooks, reschedule adapters, and managed rail-specific refund operations | Add carrier-specific status polling/webhook adapters and durable refund state machine |
| Home-server package | Single-household deployment exists; clean repo has gateway + plugin, home-server compose package, buyer setup guide, packaged skill-only ZIP, portable approval records, skill-only audit packets, idempotent `/v1/audit/import`, `/v1/audit/{purchase_id}/export`, imported-packet dashboard/order proof visibility, approval-bound payment handoff command, checked buyer-agent adapter examples for OpenClaw-style service use, Codex-style direct skill use, and generic MCP-style clients, redacted commerce ops event delivery for quote/checkout/refund/delivery-exception audit events, release manifest, release verifier, optional detached HMAC manifest signatures for private channels, upgrade/rollback notes, an external beta checklist with a validation gate, an evidence-required beta release gate with an attachable release-decision report, a production-payment env profile checker, a buyer-agent runtime test matrix covering service, direct skill, and MCP-style clients, and a prompt-injection corpus for merchant-controlled text | Self-hostable NUC/Dappnode-style stack for AgentCart, Household OS, Vikunja, Home Assistant integration, optional Woo demo | Add public asymmetric release signing or managed updates, stronger audit retention/search/permissions, plus a non-technical setup wizard |

### Current Merchant-Discovery Pilot Boundary

The Talos-hosted `registry.agentcart.eu` service is the read-only,
maintainer-curated discovery slice. Its recurring least-privilege onchain feed
is now live from the Tempo Moderato RPC `finalized` boundary, pinned to the
published runtime digest, and consumed automatically by the Direct Skill. The
two current merchant entries remain curated alpha records rather than onchain
registrations; the live contract snapshot currently contains only the
constructor ownership event.

Tempo Moderato now has an empty testnet contract. The prepared pilot merchant
has not been registered, so there is no valid claim that the public registry is
already onchain. The immediate technical sequence is:

1. deploy the published digest to the USD pilot namespace and record a real
   quote-bound Tempo payment, refund, replay rejection, and replay-store
   restart;
2. register the pilot record, index only finalized logs, verify skill-only
   discovery, revoke it, and recover through a new immutable record hash; and
3. reproduce the finalized state through an independent RPC/indexer path; and
4. repeat discovery with a non-maintainer buyer agent before inviting an
   external merchant.

Ethereum mainnet and Tempo production remain outside the approved pilot scope.
The current evidence and blockers are summarized in
`docs/TECHNICAL_PILOT_STATUS.md`.

## Non-Negotiables

- Do not scrape or automate non-opt-in shops.
- Merchant remains merchant of record.
- Quote must bind product, amount, currency, shipping country, merchant id,
  expiry, and payment requirements.
- Payment/refund verifier must reject replayed transaction references.
- Household approval must be explicit and auditable.
- Public registry must not publish household demand, addresses, private
  shopping tasks, or behavioral data.

## Production Definition Of Done

AgentCart is production-ready only when:

1. A normal WooCommerce merchant can install the plugin, understand the setup
   consequences in plain language, and configure identity, supported countries,
   support contact, payment verifier, and product exposure mode without editing
   code.
2. A buyer-side agent can discover the merchant from a signed manifest or
   registry record and get a final quote without a browser.
3. The payment verifier confirms a quote-bound payment or card authorization
   before WooCommerce marks the order paid.
4. Refunds go through the original rail and return a verifiable refund reference.
5. Delivery status can be read from WooCommerce or a carrier/shipment plugin
   without pretending merchant-estimated dates are carrier tracking.
6. Household policy and approval state are portable across Home Assistant,
   chat, web, and API clients.

## Suggested Milestones

1. **Registry transparency alpha**: merchant admin and buyer registry pages show
   current, stale, revoked, failed, and verified records with refresh/check
   actions and machine-readable reasons.
2. **Merchant alpha**: one external WooCommerce test shop can install ShopBridge
   and expose catalog/quote/order using trusted-token mode.
3. **Manifest profiles alpha**: manifests declare configured AgentCart,
   x402/MPP, Stripe/card MPP, registry, and signed-request profiles.
4. **Payment verifier alpha**: external verifier validates one real rail
   end-to-end, preferably Stripe/card EUR settlement for normal merchants.
5. **Registry source alpha**: merchant publishes signed manifest; registry stores only
   domain, manifest URL, hash, network, recipient, and timestamps.
6. **Household package alpha**: one clean NUC install runs AgentCart,
   Household OS, Vikunja, and Home Assistant integration from documented env.
7. **Production beta**: refunds, tracking, idempotency, replay protection,
   admin readiness checks, the P0 pilot checklist, and the buyer-agent runtime
   matrix are tested against real WooCommerce installs.

Current alpha hardening also includes signed-request key rotation, optional RSA
public-key verification for buyer agents that should not share symmetric
secrets, and a bounded signed-request audit trail that stores verification
outcomes and sanitized hashes instead of raw request bodies, signatures, or
nonces. ShopBridge also exposes a WooCommerce-manager support diagnostics
bundle with redacted readiness, registry, signed-request, verifier,
sandbox-check, product exposure, and WooCommerce setup summaries.
External beta readiness is tracked in `docs/PILOT_BETA_CHECKLIST.md` and
validated by `scripts/check-pilot-readiness.py`. External beta release claims
must additionally pass `scripts/collect-pilot-evidence.py`, which requires
recorded pilot evidence, recorded buyer-agent runtime evidence, a
production-shaped payment profile validated by
`scripts/check-production-payment-profile.py`, and the WooCommerce compatibility
matrix before writing an attachable release-decision report. Buyer-agent runtime
coverage is tracked in `docs/BUYER_AGENT_TEST_MATRIX.md` and validated by
`scripts/check-buyer-agent-matrix.py`. Buyer-agent adapter examples are tracked
in `docs/BUYER_AGENT_ADAPTERS.md` and validated by
`scripts/check-buyer-agent-adapter-examples.py`. AP2-style mandate mapping is
tracked in `docs/AP2_MANDATE_MAPPING.md` and validated by
`scripts/check-ap2-mandate-mapping.py`. UCP/A2A profile mapping is tracked in
`docs/UCP_A2A_PROFILES.md` and validated by
`scripts/check-ucp-a2a-profiles.py`. Merchant-text safety coverage
is tracked in `docs/PROMPT_INJECTION_CORPUS.md` and validated by
`scripts/check-prompt-injection-corpus.py`.
WooCommerce compatibility is tracked in `docs/WOOCOMMERCE_COMPATIBILITY.md` and
validated by `scripts/check-woocommerce-compatibility-matrix.py`.
The ShopBridge endpoint contract is tracked in
`docs/SHOPBRIDGE_ENDPOINT_CONTRACT.md` and validated by
`scripts/check-shopbridge-endpoint-contract.py`.
Quote reliability is tracked in `docs/QUOTE_RELIABILITY.md` and validated by
`scripts/check-quote-reliability-matrix.py`.
