# AgentCart Product Build Plan

> Status: post-hackathon execution plan. This document turns the winning demo
> into a merchant- and buyer-usable product.

## Product Direction

AgentCart should support two buyer integration paths:

1. **Skill-only buyer path**: the buyer installs an agent skill. For a known
   shop it can use a direct ShopBridge URL; for multi-merchant shopping it
   should first resolve a verified registry record, then call merchant
   discovery, quote, approval-summary, order, and status endpoints. This is the
   lowest-friction customer path.
2. **AgentCart service path**: the buyer runs the AgentCart service when they
   need durable household policy, multi-agent approval, stronger audit, delivery
   calendar/task sync, quote tournaments across many merchants, or local
   integrations.

ShopBridge remains the merchant-side WooCommerce plugin. The payment verifier
remains the settlement authority.

For standards alignment, see `docs/STANDARDS_ALIGNMENT.md`. The short version:
do not pivot the product around one protocol. Keep the AgentCart commerce core
stable, and add adapters for x402/MPP, ERC-8004, ERC-8128, ERC-8183, AP2, ACP,
UCP, MCP, and A2A at explicit seams.

## Current Product Goal

AgentCart should become the WooCommerce retail bridge for agentic commerce:
verified merchant discovery, final quote binding, explicit buyer approval,
payment-proof handoff, WooCommerce order/refund/fulfillment state, and portable
audit. The merchant path should feel like a normal WooCommerce plugin install.
The buyer path should start skill-first and require the AgentCart service only
when the household wants durable policy, audit, calendar/tasks, or stronger
local integrations.

## Next Build Sequence

| Order | Slice | Why now |
| --- | --- | --- |
| 1 | Registry transparency and refresh UX | Alpha implemented: safe multi-merchant discovery now exposes refresh/check status and machine-readable registry reasons |
| 2 | Manifest protocol profiles | Alpha implemented: manifests now publish configured-only `protocol_profiles[]` for ShopBridge commerce, MPP payment, Stripe/card MPP, and registry mapping |
| 3 | x402 compatibility shim | Alpha implemented: quote payment requirements now expose x402 exact-payment headers and checkout can answer unpaid quote-bound requests with `PAYMENT-REQUIRED` |
| 4 | Signed HTTP request verification | Alpha implemented: ShopBridge can require HMAC signed requests with method/path/digest/nonce/expiry binding for sensitive endpoints, support multiple active signing keys, rotate active signing keys with a retirement window, and buyer skill/service paths can sign them |
| 5 | Protocol translators | Next: let AP2/ACP/UCP/MCP/A2A clients use the same AgentCart quote/order model |
| 6 | Escrow/custom-order flow | Adds ERC-8183-style jobs only where normal retail checkout is the wrong model |

The immediate next implementation slice is **protocol translators**.
ShopBridge advertises `signed-http-ready` only when signed request mode and at
least one accepted request-signing key are configured. The profile publishes the
active signer id and non-secret accepted-key metadata so buyer agents can bind
checkout calls without scraping WordPress admin pages.

## Visual Architecture

```mermaid
flowchart LR
  subgraph Buyer["Buyer Side"]
    A["AI Agent"]
    S["AgentCart Skill\n(no local service)"]
    G["Optional AgentCart Service\npolicy, audit, registry, integrations"]
    M["Verified Merchant Registry\nidentity + manifest integrity"]
  end

  subgraph Merchant["Merchant Side"]
    W["WooCommerce"]
    P["ShopBridge Plugin"]
    Q["Catalog / Quote / Order / Status / Refund APIs"]
  end

  subgraph Settlement["Payment / Settlement"]
    V["External Verifier"]
    R["Payment Rail\nStripe/card MPP, Tempo, future EUR rail"]
  end

  A --> S
  S --> M
  S --> Q
  A -. optional stronger controls .-> G
  G --> M
  G --> Q
  W --> P
  P --> Q
  Q --> V
  V --> R
  R --> V
  V --> Q
```

## Execution Order

### 1. Skill-Only Buyer Alpha

Goal: a buyer can use AgentCart with only an agent skill and either a
user-specified merchant URL or a verified merchant registry record.

Deliverables:

- productize `gateway/shopbridge-direct-skill` as the lightweight buyer path;
- support manifest, catalog, quote, approval summary, order status, and checkout
  with a supplied payment receipt;
- treat `SHOPBRIDGE_BASE_URL` as a single-merchant override, not a discovery
  system;
- keep Tempo demo proof as an optional sandbox helper, not the default checkout
  model;
- add compact TOON output for agent context and JSON for payment/order calls;
- document safety limits: chat-local approval is not durable household policy.

Definition of done:

- a local agent can quote and order from a ShopBridge merchant without running
  the AgentCart service;
- checkout refuses to run without explicit approval and either a supplied
  payment receipt or configured demo proof helper;
- smoke tests cover catalog, quote, approval summary, and checkout payload
  construction.

Current alpha status: the direct ShopBridge skill can resolve verified registry
records, compare private quotes across multiple verified merchants, return the
winning full quote with an approval packet, produce an approval-bound payment
handoff for an external wallet/payment-capable agent, and reject failed
registry/domain proofs before making catalog or quote calls. It rejects
underspecified supplied payment receipts instead of filling missing amount,
currency, quote hash, destination, or rail reference from the quote. It can also
ingest the ShopBridge registry onboarding bundle as a registry source for local
single-merchant tests, and it has a read-only `doctor` command for first-run
buyer-agent configuration checks. Skill-only and service-backed approval flows
now share a portable `approval_record` / `approval_record_hash` shape; skill
checkout also emits a hash-linked `audit_packet` for later import into a
household audit trail, and the AgentCart service can import those packets
idempotently through `/v1/audit/import` and export a quote/purchase audit
bundle through `/v1/audit/{purchase_id}/export`. Production still needs durable
buyer policy, stronger audit retention/search/permissions, richer matching for
multi-item grocery baskets, and a packaged setup flow for non-technical buyers.

### 2. Merchant Alpha

Goal: a real WooCommerce merchant can expose trustworthy final quotes.

Deliverables:

- replace demo quote math with WooCommerce cart, tax, and shipping calculation;
- require a real fulfillment address for quotes;
- expose delivery methods/windows from WooCommerce or plugin settings;
- add readiness gates for HTTPS, support email, terms/refund URL, stable
  merchant id, tax/shipping setup, verifier configuration, and demo-mode status;
- support low-friction merchant-controlled product exposure modes;
- enforce per-product quantity limits, checkout exclusion overrides, category
  blocklists, product shipping-country overrides, soft quote stock holds, and
  structured restricted-goods metadata;
- expose perishable, deposit-bearing, final-sale, and substitution-sensitive
  handling metadata from normal WooCommerce tags, attributes, categories, and
  optional product-level AgentCart override switches;
- expose store-level returns, substitution, and cancellation-request defaults
  from the merchant settings page and bind them into approved quotes.

Definition of done:

- quote totals match WooCommerce checkout totals for the same basket/address;
- unsupported products, destinations, and quantities fail before payment;
- merchant admin can understand why the shop is or is not agent-ready.

Current alpha status: ShopBridge quotes through WooCommerce cart, tax, shipping,
stock, and order APIs; exposes merchant-controlled product exposure modes with
a non-mutating preview of included, blocked, and out-of-policy products;
publishes automatic and explicit item-level aftercare policy metadata; and
renders a guided setup checklist and Quick Start panel in
`WooCommerce -> AgentCart` for merchant id, agent-safe products, tax/shipping,
payment verifier, registry proof, and sandbox testing. The Quick Start panel
can prepare local sandbox access defaults, show setup progress, and surface
buyer-agent endpoint URLs without silently exposing products. It can also run a
sandbox quote check and guided checkout test through the same WooCommerce-backed
quote/order code paths used by buyer agents, then clean up the test quote,
stock hold, and test order so merchant tests do not consume availability. The plugin
publishes a registry onboarding bundle with the suggested record, proof,
revocation document, and one-entry feed so registries can ingest the shop
without merchant-side hash copy/paste. The admin registry proof panel can
refresh generated registry metadata, store a public endpoint check result for
the manifest, proof, revocation document, and bundle, and optionally submit or
revoke the current record through a merchant-configured hosted registry
connection. It can also fetch the configured registry's health and monitor JSON
so the merchant can see the current record state, manifest freshness, and last
monitor snapshot from the WooCommerce admin page. The gateway now has a
first-party alpha endpoint for that connection:
`POST /v1/registry/records` persists submitted records, verifies them with the
same domain-proof path, exposes active records at `GET /v1/registry/records`,
removes revoked hashes from the active feed, and exports submit, refresh, and
revoke events through a public hash-chained transparency log at
`GET /v1/registry/transparency`. It also exposes aggregate registry health at
`GET /v1/registry/health`. The registry page surfaces that health summary with
stale/failed/revoked alerts and operator action items. Authenticated operators
can persist snapshots and alert deltas with
`POST /v1/registry/monitor/run`, inspect them at `GET /v1/registry/monitor`,
deliver new/resolved alert changes through webhook, Home Assistant, or SMTP
email, and inspect the same delivery status from the ShopBridge WordPress admin
health panel. Buyer-side registry
entries expose `registry_status` so agents and humans can distinguish verified,
stale, revoked, local, and failed records without parsing raw verifier errors.
The same setup guide is included in the public capability document for remote
onboarding tools. The repo also includes an opt-in live smoke script for
checking manifest/capability setup state, registry bundle/proof/revocation hash
binding, catalog exposure, and WooCommerce quote totals against a seeded or
staging shop, plus a one-command WooCommerce demo smoke wrapper that starts,
seeds, and verifies the bundled local shop. The admin page can generate or
rotate local merchant and verifier tokens while respecting secrets managed
through `wp-config.php`. The pipeline also runs project-specific WordPress.org
package and review-risk guards for headers, readme metadata, external service
disclosure, superglobal unslashing, custom admin nonces, registry admin nonces,
setup-wizard admin nonces, verifier HTTP-call boundaries, Composer-pinned
PHPCS/WPCS, and an isolated official Plugin Check run. Production still needs
WP/Woo integration tests and stronger hosted registry/payment-provider
onboarding.

### 3. Idempotent Order And Replay Safety

Goal: ShopBridge can safely accept public agent checkout requests.

Deliverables:

- require idempotency keys for public order and refund calls;
- consume stored quotes atomically;
- store and reject reused payment and refund references;
- rate-limit catalog, quote, order, and verifier-triggering endpoints;
- make refund overages reject instead of silently clamp.

Definition of done:

- concurrent checkout requests cannot create duplicate paid orders;
- replayed payment references fail closed;
- verifier cost and public endpoint abuse have basic protection.

Current alpha status: the WooCommerce plugin requires order/refund idempotency
keys, locks checkout by idempotency key and merchant quote id, deletes consumed
quote transients after paid order creation, rejects reused payment/refund
references, rate-limits REST endpoints, and rejects refund overages. Production
still needs a WordPress/WooCommerce integration harness and host-level abuse
controls.

### 4. Real Settlement Path

Goal: one production-like payment rail can create and refund paid WooCommerce
orders.

Deliverables:

- choose Stripe/card MPP or Stripe-backed card settlement as the first merchant
  rail;
- bind amount, currency, merchant id/profile, quote hash, idempotency key, and
  transaction reference;
- execute refunds through the original rail;
- keep Tempo stablecoin support as a separate rail with explicit FX/settlement
  semantics.

Definition of done:

- a WooCommerce order is marked paid only after verifier success;
- a refund is recorded only after rail refund success;
- demo/test rails cannot be mistaken for production EUR settlement.

### 5. Grocery MVP

Goal: agents can do useful grocery and household replenishment, not only single
demo products.

Deliverables:

- multi-item baskets;
- pantry/favorites;
- unit price and package size comparison;
- substitutions and dietary/restricted-item policy;
- delivery slot awareness;
- recurring replenishment rules;
- aftercare commands: order status, tracking, cancellation, refund request,
  merchant support, and proof export.

Definition of done:

- an agent can replenish a small basket with approval and explain tradeoffs;
- users can inspect, cancel, refund, or contact the merchant after checkout.

Current alpha status: the direct ShopBridge skill can summarize order status,
fulfillment/tracking, refundability, merchant support, payment proof, and a
refund request draft without calling merchant-token refund, cancellation, or
order mutation endpoints. It also surfaces item-level policy review for
perishable, deposit-bearing, final-sale, substitution-sensitive, or restricted
products, plus store-level cancellation and substitution policy defaults from
the approved quote/order. The WooCommerce plugin now has a merchant-token
protected, idempotent cancellation endpoint that cancels eligible AgentCart
orders before fulfillment locks, reports when a separate rail refund is still
required, exposes an `aftercare_state` contract across order/status/refund and
cancellation responses, and normalizes tracking from common Woo shipment plugin
metadata into a stable adapter contract. The AgentCart service path now stores
and returns `aftercare_state`, enforces idempotent refund requests, rejects
refunds above the remaining refundable amount, and forwards refund idempotency
to ShopBridge. Production still needs richer refund workflows and carrier API
polling/webhooks.

Current grocery alpha status: ShopBridge exposes structured package-size
metadata from WooCommerce product weights, structured tag/dietary/allergen
metadata from normal WooCommerce product tags and attributes, and optional
product-level aftercare overrides for perishables, deposits, final-sale goods,
and substitution-sensitive items. The direct buyer skill can rank verified
merchant quotes by package/unit value, compare verified merchants by
whole-basket quotes, and handle explicit user-provided substitutions with
inherited exclusion/tag/allergen constraints. Production still needs stronger
cross-merchant basket splitting, richer dietary constraints, and pantry-aware
replenishment.

### 6. Production Packaging

Goal: the product is installable and maintainable.

Deliverables:

- buyer setup wizard or one-command package for Skill-only and service modes;
- WordPress plugin `readme.txt`, changelog, PHPCS, PHPUnit/WP integration tests,
  uninstall policy, release ZIP, and update path;
- signed merchant manifests and an identity/integrity registry;
- tamper-evident audit export and dispute packet generation.

Definition of done:

- a merchant and a buyer can install without reading the hackathon internals;
- releases have tests, versioning, and rollback/update guidance.

Current alpha status: the repo packages the WooCommerce plugin ZIP and the
skill-only buyer ZIP under `dist/`, includes WordPress release metadata
(`readme.txt`) and conservative uninstall cleanup, verifies both artifacts in
the main pipeline, compiles runtime Python files against Python 3.11 for homelab
deployment compatibility, runs the gateway Docker smoke image on Python 3.11,
runs local WordPress.org package/review-risk guards, generates
`dist/agentcart-release.json` with component versions and artifact checksums,
and documents skill-only plus home-server buyer setup and upgrade/rollback in
`docs/BUYER_SETUP.md` and `docs/RELEASES.md`. A release verifier checks manifest
schema, component versions, artifact sizes, SHA-256s, optional trusted
manifest/source pins, and optional detached HMAC release signatures for
private/self-hosted release channels. Production still needs official Plugin
Check/PHPCS, WP integration tests, public asymmetric release signing or a
managed update channel, plus a non-technical setup wizard.

### 7. Registry Alpha

Goal: agents can discover multiple opt-in merchants without trusting arbitrary
URLs or merchant-provided prompt text.

Deliverables:

- define a canonical registry record containing merchant id, domain, manifest
  URL/hash, payment recipient/network, supported countries, updated timestamp,
  revocation pointer, and signature or onchain proof;
- fetch the manifest from the registered merchant domain and verify the
  canonical hash before catalog or quote calls;
- fail closed on domain mismatch, claim/manifest hash mismatch, revoked records,
  invalid/missing advertised revocation document, invalid signature/proof, or
  payment-recipient mismatch;
- keep product catalog, prices, stock, buyer intent, address, and quotes
  off-chain and out of the public registry;
- mark merchant/product text as untrusted data so it can be summarized or
  displayed but never followed as instructions.

Definition of done:

- quote tournaments only include verified merchants unless the user explicitly
  supplies a local override;
- tests cover valid record, hash mismatch, domain mismatch, revoked record and
  matching revocation document, payment-recipient mismatch, and hostile product
  text.

## Architecture Deepening

The code should move toward these deeper modules:

1. **Purchase Lifecycle Module**
   - Files today: `gateway/agentcart.py`
   - Owns: quote, policy, approval, checkout, order, refund.
   - Benefit: purchase invariants become local and testable.

2. **State And Audit Module**
   - Files today: `gateway/agentcart.py`, JSON state/audit files.
   - Owns: quotes, approvals, challenges, idempotency, replay references,
     orders, audit events.
   - Benefit: JSON, SQLite, and Postgres adapters can satisfy the same seam.

3. **Merchant Adapter Contract**
   - Files today: `WooCommerceAdapter`, ShopBridge plugin endpoints.
   - Owns: manifest, catalog, quote, order, status, refund shapes.
   - Benefit: shared fixtures and contract tests protect every merchant adapter.

4. **Payment Verifier Module**
   - Files today: `gateway/scripts/stripe-mpp-verifier.mjs`,
     `docs/VERIFIER_CONTRACT.md`, `docs/fixtures/verifier/`, ShopBridge
     verifier calls.
   - Owns: payment/refund verification, replay checks, rail-specific binding,
     provider error classification.
   - Benefit: settlement concerns stop leaking into catalog and order code.

5. **Buyer Integration Module**
   - Files today: `gateway/shopbridge-direct-skill`,
     `gateway/openclaw-skill`, `household-os`.
   - Owns: Skill-only commands, optional service client, approval UX,
     aftercare commands.
   - Benefit: agents get a small stable interface whether the buyer runs a
     local service or not.

## Near-Term Rule

Do not add new grocery features directly into the large demo files unless the
change is already behind one of the deeper module seams above. The first
production work should make the seams deeper, then add features through them.
