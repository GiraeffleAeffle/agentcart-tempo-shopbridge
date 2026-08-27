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
| WooCommerce plugin hardening | Demo-capable ShopBridge plugin with catalog, comparison/final quote separation, country-specific complete-address enforcement before payment verification, gross-total tax metadata, order, status, refund metadata, verifier hook, admin-configurable stable merchant id, local credential generation/rotation actions, signed-request key rotation with retiring-key revocation, admin readiness checks plus a guided setup checklist and plain-language merchant setup explainer, WordPress readme/uninstall packaging metadata, WordPress.org package/review-risk guards, strict PHPCS/WPCS and Plugin Check gates, semantic-release GitHub Release artifact publishing, baseline REST rate limits, idempotent order creation, single-use quote locking, merchant-controlled product exposure modes including category mode, admin exposure preview, saved catalog snapshot diffs, category blocklist, restricted-goods default blocking with explicit per-product allow override, product-level max quantity, checkout exclusion override, product shipping-country overrides, soft quote stock holds, stale quote recovery for expiry, stock, price, shipping, and tax drift, a checked quote reliability matrix, a fail-closed hard stock reservation adapter contract, structured restricted-goods metadata, structured item commerce-policy metadata with explicit product aftercare overrides, store-level aftercare policy defaults, sandbox quote and approval-bound checkout tests, redacted merchant support diagnostics, persisted approval hashes on WooCommerce orders, merchant-approved cancellation endpoint that never executes refunds, a frozen alpha ShopBridge endpoint contract, a repeatable demo reset command, and a checked Woo/PHP/WordPress compatibility matrix with a runnable Docker smoke entry | Installable merchant plugin with strict auth, idempotency, replay protection, richer product controls, privacy defaults, tests | Add WordPress/Woo integration tests, fulfillment-aware cancellation state machine, provider-specific hard stock reservation adapters, i18n, WordPress.org release assets, and host-level WAF guidance |
| Standards alignment | AgentCart has a stable commerce core, MPP-shaped checkout, merchant registry/domain proof, rail-neutral verifier contract, skill-only buyer path, audit import/export, registry transparency state, optional ERC-8004-style identity mapping metadata, configured-only manifest protocol profiles, an x402 exact-payment compatibility shim, MCP-style tool schemas, AP2-style unsigned checkout/payment mandate mappings, UCP-style checkout mappings, A2A-style handoff profile mappings, and an HMAC/RSA signed-request alpha seam with active signer metadata and key rotation | Standards-ready retail profile with adapters for x402/MPP payments, ERC-8004 identity, ERC-8128 signed HTTP requests, signed AP2/ACP/UCP/A2A clients, and ERC-8183 custom jobs | Add native UCP/A2A protocol runtime adapters and a signed AP2 runtime adapter when a concrete conformance target is selected |
| Stripe/card, Tempo/USD, and EUR settlement | The pinned non-root verifier is live on Talos with a Bound SQLite PVC, restricted network policy, and a Tempo-only USD profile. A quote-bound pathUSD testnet payment and verifier-backed refund succeeded, a conflicting reuse returned HTTP 409, and the exact replay claims survived a pod restart and online backup. | External verifier validates real Stripe/card credentials or Tempo/x402 token transfers, executes settlement/refunds, binds results to the final quote, survives restart, and delivers actionable alerts. | Configure and test a real alert receiver, then use external merchant feedback to select and implement the first real-money EUR/card rail. |
| Merchant discovery registry | The shared trust/projection modules, immutable archive, recurring finalized indexer, direct contract-querying buyer skill, bounded query-seeded sampler, hash-committed category facets, untrusted discovery index with neutral fallback, and opt-in fail-closed cross-RPC comparison/alert mechanism are implemented. Direct discovery separates complete lifecycle replay from record-scoped eligibility failure, pins the deployment boundary, and applies chain-specific finality age. The Tempo Moderato USD merchant finalized its facet-bearing record update in transaction `0x22d1b6e5270bd2663e8d06e7049c324f04c8b6152f120fa1b827c0dc591453c8`; the unsupported EUR compatibility entry is no longer advertised. The Myotis finalized-height fix is merged upstream, but the pinned integration drill remains open. | Public identity/integrity registry with no private demand or live catalog data on-chain, replaceable routing indexes, independently reproducible finalized state, optional buyer self-verification without a full node, spam-resistant candidate membership, shared UTS-46 handling for IDN merchants, and production governance. | Drill category-routed discovery across multiple real USD/pathUSD shops; define the fixed non-ranking anti-spam registration policy; add one shared UTS-46 implementation before admitting IDN domains; activate the independent witness/alert receiver; complete the pinned Myotis drill; then obtain independent contract/governance review and non-maintainer evidence before selecting a production network. |
| Delivery tracking/refunds | Woo status endpoint returns merchant-estimated delivery plus a normalized tracking adapter contract for Woo Shipment Tracking, AfterShip-style, ParcelPanel-style, and generic order meta; delayed, failed, returned, and partial-delivery carrier exceptions now update aftercare and calendar state; refund endpoint records verifier-backed provider refund references and rejects non-real verifier responses; aftercare normalizes cancellable, locked, cancelled-refund-required, partially refunded, and refunded lifecycle states; Woo, AgentCart service, and the direct skill generate buyer aftercare messages from structured state without claiming money returned unless real refund evidence is verified | Carrier API polling/webhooks, reschedule adapters, and managed rail-specific refund operations | Add carrier-specific status polling/webhook adapters and durable refund state machine |
| Home-server package | Single-household deployment exists; clean repo has gateway + plugin, home-server compose package, buyer setup guide, packaged skill-only ZIP, portable approval records, skill-only audit packets, idempotent `/v1/audit/import`, `/v1/audit/{purchase_id}/export`, imported-packet dashboard/order proof visibility, distinct discovery/payment readiness, privacy-preserving comparison quotes, approval-bound payment handoff command, checked buyer-agent adapter examples for OpenClaw-style service use, Codex-style direct skill use, and generic MCP-style clients, redacted commerce ops event delivery for quote/checkout/refund/delivery-exception audit events, release manifest, release verifier, optional detached HMAC manifest signatures for private channels, upgrade/rollback notes, an external beta checklist with a validation gate, an evidence-required beta release gate with an attachable release-decision report, a production-payment env profile checker, a buyer-agent runtime test matrix covering service, direct skill, and MCP-style clients, and a prompt-injection corpus for merchant-controlled text | Self-hostable NUC/Dappnode-style stack for AgentCart, Household OS, Vikunja, Home Assistant integration, optional Woo demo | Add public asymmetric release signing or managed updates, stronger audit retention/search/permissions, plus a non-technical setup wizard |

### Current Merchant-Discovery Pilot Boundary

The Talos-hosted `registry.agentcart.eu` service is the read-only,
maintainer-curated compatibility, archive, and monitoring slice. Its recurring
least-privilege onchain feed reads the Tempo Moderato RPC `finalized` boundary
and is pinned to the published runtime digest. The Direct Skill now queries the
contract itself for candidate membership and lifecycle, then applies offchain
trust checks for eligibility. The unsupported EUR compatibility entry is no
longer advertised. The USD entry is controller-bound to the live testnet
contract and currently active on facet-bearing record hash
`6947c68eb613692d1fcb096ae8c330c27683aeacc79d674d2c3d7e9e75930690`.

The technical sequence through payment/refund, replay/restart, onchain
registration, revocation, recovery, skill enforcement, and two independent RPC
reconstructions is complete. The next sequence is:

1. activate the packaged registry witness with an independent full-history RPC
   and alert receiver, then record matched, firing, and resolved evidence;
2. configure the verifier alert webhook and prove delivery;
3. explicitly approve and publish the existing contract source, then retain the
   exact-match verification receipt;
4. run discovery and a quote workflow with a non-maintainer buyer agent;
5. invite an external merchant to perform the documented plugin setup while
   recording every point where maintainer help is needed; and
6. obtain security/governance review before proposing any production-network
   ADR.

Ethereum mainnet, Gnosis mainnet, and Tempo production remain outside the
approved pilot scope.
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
