# AgentCart ShopBridge

AgentCart ShopBridge is an agent-commerce bridge for WooCommerce merchants and
buyer agents. It adds the commerce layer that payment protocols alone do not
provide: merchant discovery, product catalog exposure, final quote calculation,
tax and shipping, buyer approval, quote-bound payment verification,
WooCommerce order creation, delivery visibility, refunds/cancellations, and
audit records.

Current status: production-candidate alpha. The WooCommerce plugin, buyer skill,
registry, verifier contract, package scripts, and release checks are present.
Before a real public merchant pilot, the external beta evidence gate,
production payment profile, live production-ready smoke, legal terms, and real
payment rail operations must pass.

## What Is In This Repo

```text
woocommerce-shopbridge/   WordPress/WooCommerce merchant plugin
gateway/                  AgentCart registry, verifier-facing gateway, buyer API, demos
gateway/shopbridge-direct-skill/  Service-free buyer skill for direct merchant calls
deploy/home-server/       Self-hosted buyer-side stack for household agents
household-os/             Optional Home Assistant / Vikunja / chat bridge
demo/woocommerce/         Local WooCommerce staging shop and seed script
docs/                     Production roadmap, protocol contracts, release gates
```

For independent local testing, use the Local Gateway and Home-Server Package
sections below.
For buyer-agent setup, including the packaged direct skill, see
`docs/BUYER_SETUP.md`.
For checked OpenClaw, Codex-style skill, and generic MCP buyer examples, see
`docs/BUYER_AGENT_ADAPTERS.md`.
For release artifacts, checksums, semantic-release publishing, upgrade, and
rollback, see `docs/RELEASES.md`.
For the production payment/refund verifier seam, see
`docs/VERIFIER_CONTRACT.md`.
For final quote expiry, stock, price, shipping, and tax drift handling, see
`docs/QUOTE_RELIABILITY.md`.
For standards alignment across x402/MPP, ERC-8004, ERC-8128, ERC-8183, AP2,
ACP, UCP, MCP, and A2A, see `docs/STANDARDS_ALIGNMENT.md`.
For the checked AP2-style approval/payment mandate adapter boundary, see
`docs/AP2_MANDATE_MAPPING.md`.
For the checked UCP/A2A profile mapping boundary, see
`docs/UCP_A2A_PROFILES.md`.

## Production Shape

The production path has three independent parts:

1. Merchant plugin: WooCommerce stays the product, stock, tax, shipping,
   fulfillment, refund, and support system of record. ShopBridge exposes
   agent-readable discovery, catalog, quote, order, status, refund, cancellation,
   verifier, signed-request, and registry surfaces.
2. Buyer path: buyers can use either the AgentCart gateway service or the
   packaged direct ShopBridge skill. The direct skill is the lowest-friction path
   because it can call verified merchant endpoints without running AgentCart as a
   buyer-side service.
3. Trust and payment path: merchant registry records bind the shop domain,
   manifest, proof, revocation pointer, and payment profile. External verifiers
   bind payment receipts to the quote total, currency/FX policy, merchant
   recipient/profile, quote hash, payment contract hash, and replay-safe
   transaction reference.

Local demos remain in the repo because they are useful for development,
regression testing, and onboarding. They are not the production architecture.

## Important Boundary

MPP handles payment challenge, credential, and receipt. AgentCart does not
extend core MPP for products. ShopBridge adds the commerce profile around MPP:
catalog, quote, VAT, shipping, merchant of record, order, delivery, refund, and
audit fields.
Merchant manifests publish configured-only `protocol_profiles[]` so agents can
choose the ShopBridge commerce adapter, MPP/Stripe/x402 payment adapter, or
registry/signed-request mapping before making quote calls. The x402 adapter
emits quote-bound payment requirements when configured, but WooCommerce still
marks an order paid only after the verifier confirms the receipt. Signed
request mode is optional and binds method, path, body digest, nonce, expiry,
and signer for sensitive endpoint calls.

The bundled local demo can use EUR product quotes with a pathUSD Tempo testnet
proof. That is not real EUR settlement. Production needs one of:

- merchant acceptance of stablecoin settlement and accounting;
- quote-bound FX through the verifier/payment provider contract hash plus
  replay-safe transaction references;
- Stripe/card MPP settlement;
- a future EUR-compatible MPP rail.

## Merchant Install

For a normal WordPress admin install, download `agentcart-shopbridge.zip` from a
release artifact or build it locally:

```sh
./scripts/package-woocommerce-plugin.sh
```

The generated ZIP is:

```text
dist/agentcart-shopbridge.zip
```

In WordPress, open `Plugins -> Add New -> Upload Plugin`, select the ZIP,
install, activate, then open `WooCommerce -> AgentCart`.

Before admitting a shop to a public pilot, complete the production-required
setup steps in the ShopBridge admin page:

- stable merchant id and support contact;
- WooCommerce tax, shipping, terms, and return policy setup;
- product exposure mode and blocked/restricted product review;
- external verifier URL/token and `external_verifier_only` checkout mode;
- signed request policy for sensitive endpoints;
- public HTTPS manifest, registry proof, revocation document, and registry
  bundle.

Run the live production-ready smoke against the shop:

```sh
AGENTCART_WOO_SMOKE_BASE_URL=https://shop.example.com \
AGENTCART_WOO_SMOKE_REQUIRE_SHIPPING=1 \
AGENTCART_WOO_SMOKE_REQUIRE_VAT_LINES=1 \
AGENTCART_WOO_SMOKE_REQUIRE_PRODUCTION_READY=1 \
./scripts/verify.sh
```

## Local Development Gateway

```sh
cd gateway
AGENTCART_BIND=127.0.0.1 AGENTCART_PORT=8099 python3 agentcart.py
```

Open:

```text
http://127.0.0.1:8099/presentation.html
http://127.0.0.1:8099/roadmap.html
http://127.0.0.1:8099/demo
http://127.0.0.1:8099/onboarding.html
http://127.0.0.1:8099/registry?q=Hazel%27s%20Chocolate%20Tea&country=DE&postal_code=10115
```

## Buyer Home-Server Package

```sh
cd deploy/home-server
cp .env.example .env
docker-compose up -d --build
```

Optional profiles:

```sh
docker-compose --profile homeassistant --profile woocommerce-demo up -d --build
docker-compose --profile woocommerce-demo run --rm woocommerce-seed
```

For the standalone WooCommerce ShopBridge staging shop and quote-total smoke
test:

```sh
scripts/woocommerce-demo-smoke.sh
```

This starts AgentCart, Household OS, Vikunja, and optional Home Assistant /
WooCommerce demo services. OpenClaw is expected to run separately or on the same
network with the provided skills installed.

For the lowest-friction buyer path without running AgentCart, package and
install the direct ShopBridge skill:

```sh
./scripts/package-shopbridge-direct-skill.sh
```

This creates `dist/shopbridge-direct-skill.zip`. See `docs/BUYER_SETUP.md` for
skill-only and service-backed setup. For verified multi-merchant discovery in
skill-only mode, configure `SHOPBRIDGE_REGISTRY_URL` or
`SHOPBRIDGE_REGISTRY_PATH` once instead of passing registry records every time.
If a merchant enables signed request mode, configure either the
merchant-provided `SHOPBRIDGE_SIGNED_REQUEST_SECRET` or your
`SHOPBRIDGE_SIGNED_REQUEST_PRIVATE_KEY`. The RSA path is preferred for public
or multi-merchant setups because the merchant stores only the matching public
key. Use the active signer id advertised by the merchant's `signed-http-ready`
profile as `SHOPBRIDGE_SIGNED_REQUEST_SIGNER`.

When `AGENTCART_TOKEN` is set, open protected browser pages with the token once:

```text
http://localhost:8099/?token=replace-with-random-agentcart-token
http://localhost:8099/demo?token=replace-with-random-agentcart-token
```

The query token is stored as a same-origin local demo cookie so linked pages and
browser fetches can read the protected local APIs.

## Merchant Plugin Details

The plugin ZIP is generated at:

```text
dist/agentcart-shopbridge.zip
```

To rebuild the ZIP from source:

```sh
./scripts/package-woocommerce-plugin.sh
```

The release manifest with artifact checksums is generated at:

```text
dist/agentcart-release.json
```

Private/self-hosted release channels can also publish a detached manifest
signature:

```text
dist/agentcart-release.sig
```

For a manual server install, copy `woocommerce-shopbridge/agentcart-shopbridge` into:

```text
wp-content/plugins/agentcart-shopbridge
```

A GitHub repo or ZIP does not make the plugin appear in WordPress plugin search.
The searchable `Plugins -> Add New` directory is WordPress.org's plugin
directory and requires a separate submission/review process. For private
installs before WordPress.org approval, use `Upload Plugin` with the ZIP.

After activation, open `WooCommerce -> AgentCart`. The Quick Start panel can
prepare sandbox access defaults, show setup progress, and surface the manifest,
catalog, quote, and registry bundle URLs without requiring merchants to copy
internal option names. It can also run a sandbox quote check and an
approval-bound checkout test through the same WooCommerce-backed quote/order
paths buyer agents use. The tests delete the temporary quote, release the soft
stock hold, and cancel the sandbox order so merchant testing does not consume
availability. It does not automatically expose products or configure a payment
recipient.

The Registry Proof section can also use an optional merchant-configured registry
connection URL. When configured, the merchant can submit the generated registry
bundle or send a revocation request from WordPress admin instead of copying the
bundle URL manually. The AgentCart gateway includes a first-party alpha
connection at `POST /v1/registry/records`, backed by a local JSON store and the
same domain-proof verifier used by the public registry view.

The plugin exposes:

- `/.well-known/agentcart.json`
- `/.well-known/agentcart-registry-proof.json`
- `/.well-known/agentcart-registry-revocations.json`
- `/.well-known/agentcart-registry-bundle.json`
- `/wp-json/agentcart/v1/catalog`
- `/wp-json/agentcart/v1/quote`
- `/wp-json/agentcart/v1/orders`
- `/wp-json/agentcart/v1/orders/{id}/status`
- `/wp-json/agentcart/v1/orders/{id}/refunds`
- `/wp-json/agentcart/v1/orders/{id}/cancellations`

Registry operators can ingest the plugin-generated registry bundle directly, or
build and verify merchant records from a ShopBridge manifest without
hand-writing JSON:

```sh
curl https://shop.example/.well-known/agentcart-registry-bundle.json
python3 gateway/scripts/registry_record.py build --manifest-url https://shop.example/.well-known/agentcart.json
python3 gateway/scripts/registry_record.py verify --record-file merchant-registry-record.json
```

The hosted alpha feed is available at `GET /v1/registry/records`; a compact feed
proof is available at `GET /v1/registry/feed-proof`; the normalized agent-facing
registry remains `GET /v1/registry`. Operators and agents can also check
aggregate verifier state, freshness, revocations, and action items at
`GET /v1/registry/health`. Authenticated operators can persist monitor snapshots
and alert deltas with `POST /v1/registry/monitor/run`, then read the history at
`GET /v1/registry/monitor`; set
`AGENTCART_REGISTRY_MONITOR_INTERVAL_SECONDS` to run that monitor periodically.
Set `AGENTCART_REGISTRY_ALERT_WEBHOOK_URL` or
`AGENTCART_REGISTRY_ALERT_HOMEASSISTANT_ENABLED=true` to deliver new/resolved
registry alert deltas to an operations webhook or the configured Home Assistant
notify services.

## Production Roadmap

- `docs/PRODUCTION_NEXT_STEPS.md`
- `docs/WOOCOMMERCE_PRODUCTION_HARDENING.md`
- `docs/WOOCOMMERCE_COMPATIBILITY.md`
- `docs/SETTLEMENT_OPTIONS.md`
- `docs/MERCHANT_REGISTRY.md`
- `docs/DELIVERY_AND_REFUNDS.md`
- `docs/BUYER_AGENT_TEST_MATRIX.md`
- `docs/PROMPT_INJECTION_CORPUS.md`
- `docs/PILOT_BETA_CHECKLIST.md`

These documents are roadmap/specification notes. They define the concrete work
required to move from production-candidate alpha to live merchant pilots.

## Verification

Run the full local pipeline:

```sh
bash scripts/verify.sh
```

The pipeline also compiles runtime Python files against Python 3.11, using
local `python3.11` when available or Docker `python:3.11-slim` otherwise. The
gateway Docker smoke image also runs Python 3.11, matching the current homelab
CT runtime more closely than the newest local Python.

Or run the Python tests directly:

```sh
cd gateway
python3 -m unittest discover -s tests
```

```sh
cd household-os
python3 -m unittest discover -s tests
```

Historical presentation material is kept under `docs/HACKATHON_DEMO.md`,
`docs/DEMO_RECORDING_PLAN.md`, and `docs/PROJECT_STORY.md`. It is not part of
the production install path.
