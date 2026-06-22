# AgentCart ShopBridge for Tempo MPP

AgentCart is a household-safe bridge between personal agents and opt-in
WooCommerce merchants. It demonstrates the missing commerce layer around MPP:
product discovery, final quote, household policy, human approval, payment proof,
WooCommerce order creation, delivery visibility, refund metadata, and audit.

## What Is In This Repo

```text
gateway/                  AgentCart API, household demo, pitch/architecture pages
household-os/             Home Assistant / Vikunja / OpenClaw chat bridge
woocommerce-shopbridge/   WordPress/WooCommerce plugin
demo/woocommerce/         Local WooCommerce demo shop compose files and seed script
deploy/home-server/       NUC/home-server compose package
docs/                     Hackathon story, 3-minute runbook, roadmap, protocol notes
```

For independent local testing, use the Local Gateway and Home-Server Package
sections below.
For the production payment/refund verifier seam, see
`docs/VERIFIER_CONTRACT.md`.

## Demo Flow

1. Household agent receives: "Please buy my favourite tea".
2. AgentCart resolves the household preference to Hazel's Chocolate Tea.
3. AgentCart discovers two opt-in shops and runs a private quote tournament.
4. The best quote is selected by final price, delivery, policy, and manifest
   integrity.
5. User approves the exact quote.
6. Checkout follows an MPP-shaped HTTP 402 payment flow and attaches a Tempo
   testnet proof.
7. The WooCommerce ShopBridge plugin creates the merchant order.
8. AgentCart updates Vikunja, delivery calendar, and audit state.

## Important Boundary

MPP handles payment challenge, credential, and receipt. AgentCart does not
extend core MPP for products. ShopBridge adds the commerce profile around MPP:
catalog, quote, VAT, shipping, merchant of record, order, delivery, refund, and
audit fields.

The hackathon demo uses EUR product quotes and a pathUSD Tempo testnet proof.
That is not real EUR settlement. Production needs one of:

- merchant acceptance of stablecoin settlement and accounting;
- quote-bound FX through a verifier/payment provider;
- Stripe/card MPP settlement;
- a future EUR-compatible MPP rail.

## Local Gateway

```sh
cd gateway
AGENTCART_BIND=127.0.0.1 AGENTCART_PORT=8099 python3 agentcart.py
```

Open:

```text
http://127.0.0.1:8099/presentation.html
http://127.0.0.1:8099/demo
http://127.0.0.1:8099/onboarding.html
http://127.0.0.1:8099/registry?q=Hazel%27s%20Chocolate%20Tea&country=DE&postal_code=10115
```

## Home-Server Package

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

This starts AgentCart, Household OS, Vikunja, and optional Home Assistant /
WooCommerce demo services. OpenClaw is expected to run separately or on the same
network with the provided skills installed.

When `AGENTCART_TOKEN` is set, open protected browser pages with the token once:

```text
http://localhost:8099/?token=replace-with-random-agentcart-token
http://localhost:8099/demo?token=replace-with-random-agentcart-token
```

The query token is stored as a same-origin local demo cookie so linked pages and
browser fetches can read the protected local APIs.

## WooCommerce Plugin

For a normal WordPress admin install, use the packaged plugin ZIP:

```text
dist/agentcart-shopbridge.zip
```

In WordPress, open `Plugins -> Add New -> Upload Plugin`, select the ZIP, install, activate, then open `WooCommerce -> AgentCart`.

To rebuild the ZIP from source:

```sh
./scripts/package-woocommerce-plugin.sh
```

For a manual server install, copy `woocommerce-shopbridge/agentcart-shopbridge` into:

```text
wp-content/plugins/agentcart-shopbridge
```

A GitHub repo or ZIP does not make the plugin appear in WordPress plugin search. The searchable `Plugins -> Add New` directory is WordPress.org's plugin directory and requires a separate submission/review process. For the hackathon and private installs, use `Upload Plugin` with the ZIP.

The plugin exposes:

- `/.well-known/agentcart.json`
- `/.well-known/agentcart-registry-proof.json`
- `/wp-json/agentcart/v1/catalog`
- `/wp-json/agentcart/v1/quote`
- `/wp-json/agentcart/v1/orders`
- `/wp-json/agentcart/v1/orders/{id}/status`
- `/wp-json/agentcart/v1/orders/{id}/refunds`

Registry operators can build and verify merchant records from a ShopBridge
manifest without hand-writing JSON:

```sh
python3 gateway/scripts/registry_record.py build --manifest-url https://shop.example/.well-known/agentcart.json
python3 gateway/scripts/registry_record.py verify --record-file merchant-registry-record.json
```

## Production Roadmap

- `docs/DEMO_RECORDING_PLAN.md`
- `docs/PRODUCTION_NEXT_STEPS.md`
- `docs/WOOCOMMERCE_PRODUCTION_HARDENING.md`
- `docs/SETTLEMENT_OPTIONS.md`
- `docs/MERCHANT_REGISTRY.md`
- `docs/DELIVERY_AND_REFUNDS.md`

These documents are roadmap/specification notes, not finished production features. They define the concrete work required to move from hackathon demo to production candidate.

## Verification

Run the full local pipeline:

```sh
bash scripts/verify.sh
```

Or run the Python tests directly:

```sh
cd gateway
python3 -m unittest discover -s tests
```

```sh
cd household-os
python3 -m unittest discover -s tests
```

Use `docs/HACKATHON_DEMO.md` for the full presentation runbook and
`docs/PROJECT_STORY.md` for the Devpost story.
