# AgentCart Production Tracks

> Status: roadmap/design notes. The hackathon repo implements the demo slice; this document lists production work that is not complete yet.


This file turns the hackathon "what's next" list into concrete engineering
tracks. The current repository is still a prototype; production use requires
the items below.

## Status Summary

| Track | Current state | Production target | Next implementation slice |
| --- | --- | --- | --- |
| WooCommerce plugin hardening | Demo-capable ShopBridge plugin with catalog, quote, order, status, refund metadata, verifier hook, admin readiness checks, and explicit product opt-in with a bulk onboarding action | Installable merchant plugin with strict auth, idempotency, replay protection, richer product controls, privacy defaults, tests | Add idempotency/replay tests, per-product quantity limits, and restricted-goods controls |
| Stripe/card and EUR settlement | Plugin advertises `stripe-card-mpp` only when Stripe profile + verifier are configured | External verifier can validate Stripe/card credentials, execute EUR settlement/refunds, and bind result to quote hash | Define verifier contract and sample request/response fixtures |
| Merchant discovery registry | Gateway exposes local registry page/document with stable claim or legacy manifest hashes | Public identity/integrity registry with no private demand or catalog data on-chain | Specify registry record, signing, update, revocation, and ranking rules |
| Delivery tracking/refunds | Woo status endpoint returns merchant-estimated delivery and known tracking metadata; refund endpoint records/verifies via external verifier | Carrier tracking adapters and rail-specific refund execution/verification | Define tracking adapter interface and refund state machine |
| Home-server package | Single-household deployment exists; clean repo has gateway + plugin | Self-hostable NUC/Dappnode-style stack for AgentCart, Household OS, Vikunja, Home Assistant integration, optional Woo demo | Add `deploy/home-server` compose package and onboarding docs |

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
   supported countries, support contact, payment verifier, and per-product
   opt-in without editing code.
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

1. **Merchant alpha**: one external WooCommerce test shop can install ShopBridge
   and expose catalog/quote/order using trusted-token mode.
2. **Payment verifier alpha**: external verifier validates one real rail
   end-to-end, preferably Stripe/card EUR settlement for normal merchants.
3. **Registry alpha**: merchant publishes signed manifest; registry stores only
   domain, manifest URL, hash, network, recipient, and timestamps.
4. **Household package alpha**: one clean NUC install runs AgentCart,
   Household OS, Vikunja, and Home Assistant integration from documented env.
5. **Production beta**: refunds, tracking, idempotency, replay protection, and
   admin readiness checks are tested.
