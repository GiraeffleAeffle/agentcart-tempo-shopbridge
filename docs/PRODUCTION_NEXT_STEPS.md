# AgentCart Production Tracks

> Status: production-candidate alpha with explicit production gaps. This
> document separates implemented capabilities from the remaining gates required
> before live merchant pilots.

This file turns the production roadmap into concrete engineering tracks.
Production use requires the remaining items below.

The standards direction is tracked in `docs/STANDARDS_ALIGNMENT.md`: AgentCart
keeps a stable commerce core and adds adapters for x402/MPP, ERC-8004,
ERC-8128, ERC-8183, AP2, ACP, UCP, MCP, and A2A at explicit seams.

## Status Summary

| Track | Current state | Production target | Next implementation slice |
| --- | --- | --- | --- |
| WooCommerce plugin hardening | Demo-capable ShopBridge plugin with catalog, quote, order, status, refund metadata, verifier hook, admin-configurable stable merchant id, local credential generation/rotation actions, signed-request key rotation with retiring-key revocation, admin readiness checks plus a guided setup checklist, WordPress readme/uninstall packaging metadata, WordPress.org package/review-risk guards, strict PHPCS/WPCS and Plugin Check gates, semantic-release GitHub Release artifact publishing, baseline REST rate limits, idempotent order creation, single-use quote locking, merchant-controlled product exposure modes including category mode, admin exposure preview, saved catalog snapshot diffs, category blocklist, restricted-goods default blocking with explicit per-product allow override, product-level max quantity, checkout exclusion override, product shipping-country overrides, soft quote stock holds, stale quote recovery for expiry, stock, price, shipping, and tax drift, a checked quote reliability matrix, a fail-closed hard stock reservation adapter contract, structured restricted-goods metadata, structured item commerce-policy metadata with explicit product aftercare overrides, store-level aftercare policy defaults, sandbox quote and approval-bound checkout tests, redacted merchant support diagnostics, persisted approval hashes on WooCommerce orders, merchant-approved cancellation endpoint that never executes refunds, and a checked Woo/PHP/WordPress compatibility matrix with a runnable Docker smoke entry | Installable merchant plugin with strict auth, idempotency, replay protection, richer product controls, privacy defaults, tests | Add WordPress/Woo integration tests, fulfillment-aware cancellation state machine, provider-specific hard stock reservation adapters, i18n, WordPress.org release assets, and host-level WAF guidance |
| Standards alignment | AgentCart has a stable commerce core, MPP-shaped checkout, merchant registry/domain proof, rail-neutral verifier contract, skill-only buyer path, audit import/export, registry transparency state, optional ERC-8004-style identity mapping metadata, configured-only manifest protocol profiles, an x402 exact-payment compatibility shim, MCP-style tool schemas, AP2-style unsigned checkout/payment mandate mappings, UCP-style checkout mappings, A2A-style handoff profile mappings, and an HMAC/RSA signed-request alpha seam with active signer metadata and key rotation | Standards-ready retail profile with adapters for x402/MPP payments, ERC-8004 identity, ERC-8128 signed HTTP requests, signed AP2/ACP/UCP/A2A clients, and ERC-8183 custom jobs | Add native UCP/A2A protocol runtime adapters and a signed AP2 runtime adapter when a concrete conformance target is selected |
| Stripe/card and EUR settlement | Plugin advertises `stripe-card-mpp` only when Stripe profile + verifier are configured; checked-in positive/negative fixtures pin the payment/refund verifier contract; sandbox verifier has lock-protected file-backed replay storage, a fail-closed durable replay readiness gate, append-only sanitized replay journal, health diagnostics, JSON metrics, structured request logs, replay conflict counters, verifier failure webhooks, provider error classification, and verifier-backed refund evidence that AgentCart validates before marking a refund real | External verifier can validate Stripe/card credentials, execute EUR settlement/refunds, and bind result to quote hash | Move replay storage/metrics into a managed transactional store and add provider-specific dashboards |
| Merchant discovery registry | Gateway and direct skill verify stable claims, domain proofs, endpoint scope, payment binding, stale records, merchant-hosted revocation documents, and optional ERC-8004-style onchain identity mappings; ShopBridge publishes a registry onboarding bundle that loaders can ingest as a feed; merchant admin can refresh/check public registry endpoints, submit/revoke records to the hosted alpha registry, and fetch registry-side health/monitor state plus alert delivery results; gateway entries expose `registry_status`; registry health summarizes stale/failed/revoked records and operator action items; hosted submit/refresh/revoke actions append to a public hash-chained transparency log; the hosted feed exposes a canonical feed proof over active records, revocations, and transparency head; authenticated monitor runs persist snapshots and alert deltas and can deliver them through webhook, Home Assistant, or SMTP email | Public identity/integrity registry with no private demand or catalog data on-chain, with a clean path to ERC-8004 registration metadata | Move record source to an append-only/onchain registry, add operator governance, public signing/onchain anchoring for feed proofs, and harden alert operations |
| Delivery tracking/refunds | Woo status endpoint returns merchant-estimated delivery plus a normalized tracking adapter contract for Woo Shipment Tracking, AfterShip-style, ParcelPanel-style, and generic order meta; delayed, failed, returned, and partial-delivery carrier exceptions now update aftercare and calendar state; refund endpoint records verifier-backed provider refund references and rejects non-real verifier responses; aftercare normalizes cancellable, locked, cancelled-refund-required, partially refunded, and refunded lifecycle states; Woo, AgentCart service, and the direct skill generate buyer aftercare messages from structured state without claiming money returned unless real refund evidence is verified | Carrier API polling/webhooks, reschedule adapters, and managed rail-specific refund operations | Add carrier-specific status polling/webhook adapters and durable refund state machine |
| Home-server package | Single-household deployment exists; clean repo has gateway + plugin, home-server compose package, buyer setup guide, packaged skill-only ZIP, portable approval records, skill-only audit packets, idempotent `/v1/audit/import`, `/v1/audit/{purchase_id}/export`, imported-packet dashboard/order proof visibility, approval-bound payment handoff command, checked buyer-agent adapter examples for OpenClaw-style service use, Codex-style direct skill use, and generic MCP-style clients, redacted commerce ops event delivery for quote/checkout/refund/delivery-exception audit events, release manifest, release verifier, optional detached HMAC manifest signatures for private channels, upgrade/rollback notes, an external beta checklist with a validation gate, an evidence-required beta release gate, a production-payment env profile checker, a buyer-agent runtime test matrix covering service, direct skill, and MCP-style clients, and a prompt-injection corpus for merchant-controlled text | Self-hostable NUC/Dappnode-style stack for AgentCart, Household OS, Vikunja, Home Assistant integration, optional Woo demo | Add public asymmetric release signing or managed updates, stronger audit retention/search/permissions, plus a non-technical setup wizard |

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

1. A normal WooCommerce merchant can install the plugin, configure identity,
   supported countries, support contact, payment verifier, and product exposure
   mode without editing code.
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
must additionally pass `scripts/check-beta-release-readiness.py`, which requires
recorded pilot evidence, recorded buyer-agent runtime evidence, and a
production-shaped payment profile validated by
`scripts/check-production-payment-profile.py`. Buyer-agent runtime coverage
is tracked in `docs/BUYER_AGENT_TEST_MATRIX.md` and validated by
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
Quote reliability is tracked in `docs/QUOTE_RELIABILITY.md` and validated by
`scripts/check-quote-reliability-matrix.py`.
